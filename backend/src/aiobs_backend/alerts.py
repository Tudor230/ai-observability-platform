"""Alert & budget engine (plans/backend.md §10).

v1 rules derive from configured budgets: utilization >= 100% → critical
"budget exceeded"; >= 80% → warning "budget approaching". Dedupes against open
alerts per rule so repeated evaluations do not spam.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Alert, Budget, Execution

WARN_AT = 0.8
CRITICAL_AT = 1.0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def budget_spend(
    session: Session, budget: Budget, now: datetime | None = None
) -> float:
    now = now or _utcnow()
    q = select(func.coalesce(func.sum(Execution.total_cost), 0)).where(
        Execution.started_at >= budget.period,
        Execution.started_at < now,
    )
    if budget.project_id:
        q = q.where(Execution.project_id == budget.project_id)
    if budget.client_id:
        q = q.where(Execution.client_id == budget.client_id)
    if budget.workflow_name:
        q = q.where(Execution.workflow_name == budget.workflow_name)
    return float(session.execute(q).scalar_one())


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
    amount = float(budget.amount or 0)
    if amount <= 0:
        return []
    utilization = spend / amount
    period = budget.period.isoformat()
    label = budget.name or f"budget {period}"
    created: list[Alert] = []

    for severity, reached, message in (
        (
            "critical",
            utilization >= CRITICAL_AT,
            f"Budget exceeded: {label} spent {spend:.2f} of {amount:.2f} ({utilization:.0%})",
        ),
        (
            "warning",
            utilization >= WARN_AT,
            f"Budget approaching: {label} spent {spend:.2f} of {amount:.2f} ({utilization:.0%})",
        ),
    ):
        if not reached:
            continue
        rule_id = f"budget:{budget.id}:{severity}"
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


def evaluate_alerts(
    session: Session, now: datetime | None = None
) -> list[dict]:
    now = now or _utcnow()
    created: list[Alert] = []
    for budget in session.execute(select(Budget)).scalars():
        created.extend(evaluate_budget(session, budget, now))
    session.flush()
    return [
        {
            "id": a.id,
            "rule_id": a.rule_id,
            "severity": a.severity,
            "message": a.message,
            "dimension": a.dimension,
            "dimension_key": a.dimension_key,
            "status": a.status,
            "triggered_at": a.triggered_at.isoformat(),
        }
        for a in created
    ]