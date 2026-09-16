"""Workflows: aggregated list view (cost/latency/success per workflow name)."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...models import Execution
from ..deps import get_db, get_project_scope, require_role
from ..queries import default_range, exec_aggregates, parse_dt
from ..serialize import money

router = APIRouter(tags=["workflows"], dependencies=[Depends(require_role("sdm", "finance"))])


@router.get("/workflows")
def list_workflows(
    session: Session = Depends(get_db),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    days: int = Query(default=90, ge=1, le=3650),
    project_id: str | None = Query(default=None),
    client_id: str | None = Query(default=None),
    project_scope: str | None = Depends(get_project_scope),
) -> dict:
    end_dt = parse_dt(end, end_of_day=True) or default_range(days)[1]
    start_dt = parse_dt(start) or (end_dt - timedelta(days=days))
    rows = exec_aggregates(
        session,
        group_col=Execution.workflow_name,
        start=start_dt,
        end=end_dt,
        project_id=project_id or project_scope,
        client_id=client_id,
    )
    items = []
    for row in rows:
        n = row.executions
        items.append(
            {
                "name": row.key or "unknown",
                "executions": n,
                "failed_executions": row.failed,
                "error_rate": round(row.failed / n, 4) if n else 0.0,
                "total_cost": money(row.total_cost),
                "total_tokens": row.total_tokens,
                "avg_duration_ms": round(float(row.avg_duration_ms or 0), 2),
                "last_seen": row.last_seen.isoformat() if row.last_seen else None,
            }
        )
    items.sort(key=lambda i: i["total_cost"] or 0, reverse=True)
    return {"items": items, "total": len(items)}
