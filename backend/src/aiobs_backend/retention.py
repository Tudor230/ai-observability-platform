"""Data retention (F35): purge platform rows older than the configured window.

Retention is opt-in (``AIOBS_RETENTION_DAYS=0`` keeps data forever). When set,
executions, their spans and cost records, daily metrics and alerts older than
the window are deleted; dimension rows (clients/workflows/agents) are kept as
attribution history.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import Alert, CostRecord, DailyMetric, Execution, Span


def purge_expired(
    session: Session, retention_days: int, now: datetime | None = None
) -> dict:
    """Delete rows older than ``retention_days``; returns per-table counts."""
    result = {
        "executions": 0,
        "spans": 0,
        "cost_records": 0,
        "daily_metrics": 0,
        "alerts": 0,
    }
    if retention_days <= 0:
        return result
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=retention_days)

    execution_ids = list(
        session.execute(
            select(Execution.id).where(Execution.started_at < cutoff)
        ).scalars()
    )
    if execution_ids:
        result["cost_records"] = session.execute(
            delete(CostRecord).where(CostRecord.execution_id.in_(execution_ids))
        ).rowcount
        result["spans"] = session.execute(
            delete(Span).where(Span.execution_id.in_(execution_ids))
        ).rowcount
        result["executions"] = session.execute(
            delete(Execution).where(Execution.id.in_(execution_ids))
        ).rowcount
    result["daily_metrics"] = session.execute(
        delete(DailyMetric).where(DailyMetric.day < cutoff.date().isoformat())
    ).rowcount
    result["alerts"] = session.execute(
        delete(Alert).where(Alert.triggered_at < cutoff)
    ).rowcount
    session.flush()
    return result
