"""Alert & budget engine (plans/backend.md §10).

v1 rules derive from configured budgets: utilization >= 100% → critical
"budget exceeded"; >= 80% → warning "budget approaching". Spend is computed
inside the budget's *current window* (day/week/month, anchored at
``Budget.period``), so budgets reset every period instead of accumulating
forever (F09). Dedupes against open alerts per rule (and per window) so repeated
evaluations do not spam.
"""
from __future__ import annotations

import calendar
import json
import logging
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import Alert, AlertRule, Budget, Execution, Project, Team
from .stats import percentile

logger = logging.getLogger(__name__)

WARN_AT = 0.8
CRITICAL_AT = 1.0
PERIOD_TYPES = ("day", "week", "month")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def budget_window(
    budget: Budget, now: datetime | None = None
) -> tuple[datetime, datetime]:
    """Current spend window ``[start, end)`` for a budget (F09).

    - ``day``: the UTC day containing ``now``
    - ``week``: 7-day periods counted from the anchor
    - ``month``: calendar months aligned to the anchor's day (clamped to the
      month's length, so a 31st anchor works in February)
    """
    now = now or _utcnow()
    anchor = budget.period
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    period_type = budget.period_type or "month"

    if period_type == "day":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)

    if period_type == "week":
        step = timedelta(weeks=1)
        periods = (now - anchor) // step
        start = anchor + periods * step
        return start, start + step

    def index(d: datetime) -> int:
        return d.year * 12 + (d.month - 1)

    def month_start(base_index: int) -> datetime:
        year, month = divmod(base_index, 12)
        month += 1
        day = min(anchor.day, calendar.monthrange(year, month)[1])
        return anchor.replace(year=year, month=month, day=day)

    idx = index(now)
    start = month_start(idx)
    if start > now:
        # Anchor day (e.g. 31) clamped past `now` this month: use the previous
        # clamped month so the window still contains `now`.
        end = start
        start = month_start(idx - 1)
    else:
        end = month_start(idx + 1)
    return start, end


def budget_spend(
    session: Session, budget: Budget, now: datetime | None = None
) -> float:
    now = now or _utcnow()
    start, end = budget_window(budget, now)
    end = min(end, now)  # only realized spend inside the current window
    q = select(func.coalesce(func.sum(Execution.total_cost), 0)).where(
        Execution.started_at >= start,
        Execution.started_at < end,
    )
    if budget.project_id:
        q = q.where(Execution.project_id == budget.project_id)
    if budget.client_id:
        q = q.where(Execution.client_id == budget.client_id)
    if budget.workflow_name:
        q = q.where(Execution.workflow_name == budget.workflow_name)
    if budget.team_id or budget.department_id:
        # Department/team budgets only count executions under their unit.
        q = q.join(Project, Project.id == Execution.project_id).join(
            Team, Team.id == Project.team_id
        )
        if budget.team_id:
            q = q.where(Team.id == budget.team_id)
        if budget.department_id:
            q = q.where(Team.department_id == budget.department_id)
    return float(session.execute(q).scalar_one() or 0)


def _has_open(session: Session, rule_id: str) -> bool:
    return (
        session.execute(
            select(Alert.id).where(
                Alert.rule_id == rule_id, Alert.status == "open"
            )
        ).first()
        is not None
    )


def evaluate_budget(
    session: Session, budget: Budget, now: datetime | None = None
) -> list[Alert]:
    now = now or _utcnow()
    spend = budget_spend(session, budget, now)
    amount = float(budget.amount or Decimal("0"))
    if amount <= 0:
        return []
    utilization = spend / amount
    window_start, window_end = budget_window(budget, now)
    period = (
        f"{window_start.date().isoformat()}..{window_end.date().isoformat()} "
        f"({budget.period_type or 'month'})"
    )
    label = budget.name or "budget"
    created: list[Alert] = []

    for severity, reached, message in (
        (
            "critical",
            utilization >= CRITICAL_AT,
            f"Budget exceeded: {label} spent {spend:.2f} of {amount:.2f} ({utilization:.0%}) in {period}",
        ),
        (
            "warning",
            utilization >= WARN_AT,
            f"Budget approaching: {label} spent {spend:.2f} of {amount:.2f} ({utilization:.0%}) in {period}",
        ),
    ):
        if not reached:
            continue
        rule_id = f"budget:{budget.id}:{window_start.date().isoformat()}:{severity}"
        if _has_open(session, rule_id):
            continue
        alert = Alert(
            rule_id=rule_id,
            severity=severity,
            message=message,
            dimension="budget",
            dimension_key=budget.id,
            status="open",
            triggered_at=now,
        )
        session.add(alert)
        created.append(alert)
    return created


METRICS = (
    "error_rate",
    "daily_tokens",
    "tool_calls_per_execution",
    "p95_latency",
    "cost_anomaly",
)


def _scope_internal_project_ids(session: Session, rule) -> set[str] | None:
    """Internal project ids a rule applies to; ``None`` = every project."""
    if rule.scope_type == "global" or not rule.scope_id:
        return None
    if rule.scope_type == "project":
        return {rule.scope_id} if session.get(Project, rule.scope_id) else set()
    stmt = select(Project.id).join(Team, Team.id == Project.team_id)
    if rule.scope_type == "team":
        stmt = stmt.where(Project.team_id == rule.scope_id)
    elif rule.scope_type == "department":
        stmt = stmt.where(Team.department_id == rule.scope_id)
    else:
        return set()
    return set(session.execute(stmt).scalars().all())


def _baseline_cost_per_day(
    session: Session, day_start: datetime, project_ids: set[str] | None
) -> float:
    """7-day average daily cost before ``day_start`` (scope-restricted)."""
    if project_ids is not None and not project_ids:
        return 0.0
    q = select(func.coalesce(func.sum(Execution.total_cost), 0)).where(
        Execution.started_at >= day_start - timedelta(days=7),
        Execution.started_at < day_start,
    )
    if project_ids is not None:
        q = q.where(Execution.project_id.in_(project_ids))
    return float(session.execute(q).scalar_one() or 0) / 7


def _fmt_value(metric: str, value: float) -> str:
    if metric == "error_rate":
        return f"{value:.0%}"
    if metric == "daily_tokens":
        return f"{value:,.0f} tokens"
    if metric == "tool_calls_per_execution":
        return f"{value:.1f} tool calls/execution"
    if metric == "p95_latency":
        return f"{value:.0f}ms"
    if metric == "cost_anomaly":
        return f"{value:.1f}x the 7-day average"
    return f"{value:.2f}"


def _rule_message(rule, value: float, threshold: float, day: str) -> str:
    scope = "all projects" if rule.scope_type == "global" else f"{rule.scope_type} scope"
    return (
        f"{rule.name}: {_fmt_value(rule.metric, value)} today exceeds "
        f"{_fmt_value(rule.metric, threshold)} ({scope}, {day})"
    )


def evaluate_threshold_rules(
    session: Session, now: datetime | None = None
) -> list[Alert]:
    """Day-scoped consumption/quality rules from the `alert_rules` table.

    Built-in rules are seeded from the old env thresholds (F04); user rules
    carry their own warning/critical thresholds and org scope. Each rule is
    evaluated over its scope's executions for the current UTC day and deduped
    per ``(rule, day, severity)``.
    """
    settings = get_settings()
    now = now or _utcnow()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day = day_start.date().isoformat()
    rules = (
        session.execute(select(AlertRule).where(AlertRule.enabled.is_(True)))
        .scalars()
        .all()
    )
    if not rules:
        return []
    rows = (
        session.execute(
            select(Execution).where(
                Execution.started_at >= day_start, Execution.started_at < now
            )
        )
        .scalars()
        .all()
    )
    created: list[Alert] = []

    for rule in rules:
        scope_ids = _scope_internal_project_ids(session, rule)
        scoped = rows if scope_ids is None else [e for e in rows if e.project_id in scope_ids]
        count = len(scoped)
        if count < settings.alert_min_executions:
            continue

        metric = rule.metric
        if metric == "error_rate":
            value = sum(1 for e in scoped if e.status == "error") / count
        elif metric == "daily_tokens":
            value = float(sum(e.total_tokens for e in scoped))
        elif metric == "tool_calls_per_execution":
            value = sum(e.tool_calls for e in scoped) / count
        elif metric == "p95_latency":
            value = percentile(
                [e.duration_ms for e in scoped if e.duration_ms is not None], 0.95
            )
        elif metric == "cost_anomaly":
            baseline = _baseline_cost_per_day(session, day_start, scope_ids)
            if baseline <= 0:
                continue
            value = sum(float(e.total_cost or 0) for e in scoped) / baseline
        else:
            continue

        warning = float(rule.warning_threshold)
        critical = float(rule.critical_threshold)
        for severity, threshold in (("critical", critical), ("warning", warning)):
            if value < threshold:
                continue
            rule_key = f"rule:{rule.id}:{day}:{severity}"
            if _has_open(session, rule_key):
                continue
            alert = Alert(
                rule_id=rule_key,
                rule_ref=rule.id,
                severity=severity,
                message=_rule_message(rule, value, threshold, day),
                dimension="rule",
                dimension_key=metric,
                status="open",
                triggered_at=now,
            )
            session.add(alert)
            created.append(alert)

    return created


def _alert_dict(a: Alert) -> dict:
    return {
        "id": a.id,
        "rule_id": a.rule_id,
        "rule_ref": a.rule_ref,
        "severity": a.severity,
        "message": a.message,
        "dimension": a.dimension,
        "dimension_key": a.dimension_key,
        "status": a.status,
        "triggered_at": a.triggered_at.isoformat() if a.triggered_at else None,
    }


def _notify_webhook(alerts: list[Alert]) -> None:
    """Best-effort webhook delivery for newly created alerts (F37).

    Delivery failures never affect evaluation: they are logged and the alert
    remains available through the API/UI.
    """
    settings = get_settings()
    if not alerts or not settings.alert_webhook_url:
        return
    payload = json.dumps({"alerts": [_alert_dict(a) for a in alerts]}).encode("utf-8")
    request = urllib.request.Request(
        settings.alert_webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request, timeout=settings.alert_webhook_timeout_s
        ):
            pass
    except Exception:
        logger.warning("alert webhook delivery failed", exc_info=True)


def evaluate_alerts(
    session: Session, now: datetime | None = None
) -> list[dict]:
    now = now or _utcnow()
    created: list[Alert] = []
    for budget in session.execute(select(Budget)).scalars():
        created.extend(evaluate_budget(session, budget, now))
    created.extend(evaluate_threshold_rules(session, now))
    session.flush()
    _notify_webhook(created)
    return [_alert_dict(a) for a in created]