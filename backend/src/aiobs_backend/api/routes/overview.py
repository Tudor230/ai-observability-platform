"""Top-line KPIs for the dashboard landing view."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Alert, Execution
from ...stats import percentile
from ..deps import get_db, get_project_scope, require_role
from ..queries import default_range, exec_rows, parse_dt

router = APIRouter(tags=["overview"], dependencies=[Depends(require_role())])


def _window_stats(session: Session, start, end, **extra) -> dict:
    rows = session.execute(
        exec_rows(session, start=start, end=end, **extra).with_only_columns(
            Execution.total_cost,
            Execution.total_tokens,
            Execution.duration_ms,
            Execution.status,
            Execution.llm_calls,
            Execution.tool_calls,
        )
    ).all()
    n = len(rows)
    failed = sum(1 for r in rows if r.status == "error")
    durations = [r.duration_ms for r in rows if r.duration_ms is not None]
    total_cost = sum(
        (r.total_cost or Decimal("0") for r in rows), Decimal("0")
    )
    return {
        "executions": n,
        "failed_executions": failed,
        "error_rate": round(failed / n, 4) if n else 0.0,
        "total_cost": round(float(total_cost), 6),
        "total_tokens": sum(r.total_tokens or 0 for r in rows),
        "llm_calls": sum(r.llm_calls or 0 for r in rows),
        "tool_calls": sum(r.tool_calls or 0 for r in rows),
        "avg_duration_ms": round(sum(durations) / len(durations), 2) if durations else 0.0,
        "p50_duration_ms": round(percentile(durations, 0.5), 2),
        "p95_duration_ms": round(percentile(durations, 0.95), 2),
        "p99_duration_ms": round(percentile(durations, 0.99), 2),
    }


def _pct(current: float, previous: float) -> float | None:
    if not previous:
        return None
    return round((current - previous) / previous * 100.0, 2)


@router.get("/overview")
def overview(
    session: Session = Depends(get_db),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    days: int = Query(default=30, ge=1, le=3650),
    project_id: str | None = Query(default=None),
    client_id: str | None = Query(default=None),
    workflow: str | None = Query(default=None),
    project_scope: str | None = Depends(get_project_scope),
) -> dict:
    now = parse_dt(end) if end else None
    now = now or default_range(days)[1]
    window_start = parse_dt(start)
    if window_start is None:
        window_start = now - timedelta(days=days)
    project_id = project_id or project_scope

    current = _window_stats(
        session, window_start, now, project_id=project_id, client_id=client_id, workflow=workflow
    )
    span = now - window_start
    previous = _window_stats(
        session, window_start - span, window_start,
        project_id=project_id, client_id=client_id, workflow=workflow,
    )
    open_alerts = session.execute(select(Alert).where(Alert.status == "open")).scalars().all()
    return {
        **current,
        "deltas": {
            "total_cost_pct": _pct(current["total_cost"], previous["total_cost"]),
            "executions_pct": _pct(current["executions"], previous["executions"]),
            "error_rate_pct": _pct(current["error_rate"], previous["error_rate"]),
        },
        "open_alerts": len(open_alerts),
    }