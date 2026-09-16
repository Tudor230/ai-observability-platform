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
from .models import Alert, Budget, Execution
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


def _severity(value: float, threshold: float) -> str:
    return "critical" if value >= threshold * 2 else "warning"


def _rule_alert(
    session: Session,
    *,
    rule_id: str,
    severity: str,
    message: str,
    dimension_key: str,
    now: datetime,
) -> Alert | None:
    if _has_open(session, rule_id):
        return None
    alert = Alert(
        rule_id=rule_id,
        severity=severity,
        message=message,
        dimension="rule",
        dimension_key=dimension_key,
        status="open",
        triggered_at=now,
    )
    session.add(alert)
    return alert


def evaluate_threshold_rules(
    session: Session, now: datetime | None = None
) -> list[Alert]:
    """Day-scoped consumption/quality rules (F04, plans/backend.md §10).

    Covers the non-budget categories promised in docs/03 §3.12: error rate,
    daily tokens, p95 latency, excessive tool calls, and cost deviation from
    the 7-day moving average. Rules are deduped per rule id, which includes
    the day, so each rule can alert once per day.
    """
    settings = get_settings()
    now = now or _utcnow()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    rows = (
        session.execute(
            select(Execution).where(
                Execution.started_at >= day_start, Execution.started_at < now
            )
        )
        .scalars()
        .all()
    )
    if len(rows) < settings.alert_min_executions:
        return []

    day = day_start.date().isoformat()
    count = len(rows)
    created: list[Alert] = []

    failed = sum(1 for e in rows if e.status == "error")
    rate = failed / count
    if rate >= settings.alert_error_rate:
        alert = _rule_alert(
            session,
            rule_id=f"rule:error_rate:{day}",
            severity=_severity(rate, settings.alert_error_rate),
            message=(
                f"Error rate {rate:.0%} today ({failed}/{count} executions) "
                f"exceeds {settings.alert_error_rate:.0%}"
            ),
            dimension_key="error_rate",
            now=now,
        )
        if alert:
            created.append(alert)

    tokens = sum(e.total_tokens for e in rows)
    if tokens >= settings.alert_daily_tokens:
        alert = _rule_alert(
            session,
            rule_id=f"rule:tokens:{day}",
            severity=_severity(tokens, settings.alert_daily_tokens),
            message=(
                f"Daily token consumption {tokens:,} exceeds "
                f"{settings.alert_daily_tokens:,}"
            ),
            dimension_key="tokens",
            now=now,
        )
        if alert:
            created.append(alert)

    tool_calls_per_exec = sum(e.tool_calls for e in rows) / count
    if tool_calls_per_exec >= settings.alert_tool_calls_per_execution:
        alert = _rule_alert(
            session,
            rule_id=f"rule:tool_calls:{day}",
            severity=_severity(tool_calls_per_exec, settings.alert_tool_calls_per_execution),
            message=(
                f"Tool calls per execution {tool_calls_per_exec:.1f} exceeds "
                f"{settings.alert_tool_calls_per_execution:.1f} (agent loop?)"
            ),
            dimension_key="tool_calls",
            now=now,
        )
        if alert:
            created.append(alert)

    p95 = percentile(
        [e.duration_ms for e in rows if e.duration_ms is not None], 0.95
    )
    if p95 >= settings.alert_p95_latency_ms:
        alert = _rule_alert(
            session,
            rule_id=f"rule:latency_p95:{day}",
            severity=_severity(p95, settings.alert_p95_latency_ms),
            message=(
                f"P95 execution latency {p95:.0f}ms exceeds "
                f"{settings.alert_p95_latency_ms:.0f}ms today"
            ),
            dimension_key="latency_p95",
            now=now,
        )
        if alert:
            created.append(alert)

    today_cost = sum(float(e.total_cost or 0) for e in rows)
    baseline_start = day_start - timedelta(days=7)
    baseline_total = float(
        session.execute(
            select(func.coalesce(func.sum(Execution.total_cost), 0)).where(
                Execution.started_at >= baseline_start,
                Execution.started_at < day_start,
            )
        ).scalar_one()
        or 0
    )
    baseline_per_day = baseline_total / 7
    if (
        baseline_per_day > 0
        and today_cost >= baseline_per_day * settings.alert_cost_anomaly_factor
    ):
        alert = _rule_alert(
            session,
            rule_id=f"rule:cost_anomaly:{day}",
            severity=_severity(
                today_cost, baseline_per_day * settings.alert_cost_anomaly_factor
            ),
            message=(
                f"Today's cost {today_cost:.4f} is "
                f"{today_cost / baseline_per_day:.1f}x the 7-day average "
                f"({baseline_per_day:.4f}/day)"
            ),
            dimension_key="cost_anomaly",
            now=now,
        )
        if alert:
            created.append(alert)

    return created


def _alert_dict(a: Alert) -> dict:
    return {
        "id": a.id,
        "rule_id": a.rule_id,
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