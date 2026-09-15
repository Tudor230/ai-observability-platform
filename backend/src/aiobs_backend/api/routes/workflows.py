"""Workflows: aggregated list view (cost/latency/success per workflow name)."""
from __future__ import annotations

from datetime import timedelta
from statistics import fmean

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..deps import get_db, get_project_scope, require_read_access
from ..queries import default_range, fetch_exec_rows, parse_dt
from ..serialize import money

router = APIRouter(tags=["workflows"], dependencies=[Depends(require_read_access)])


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
    rows = fetch_exec_rows(
        session, start=start_dt, end=end_dt, project_id=project_id or project_scope, client_id=client_id
    )
    agg: dict[str, dict] = {}
    for ex, *_ in rows:
        name = ex.workflow_name or "unknown"
        bucket = agg.setdefault(
            name,
            {
                "name": name,
                "executions": 0,
                "failed": 0,
                "cost": 0.0,
                "tokens": 0,
                "durations": [],
                "last_seen": None,
            },
        )
        bucket["executions"] += 1
        if ex.status == "error":
            bucket["failed"] += 1
        bucket["cost"] += float(ex.total_cost or 0)
        bucket["tokens"] += ex.total_tokens
        if ex.duration_ms is not None:
            bucket["durations"].append(ex.duration_ms)
        seen = ex.started_at
        if seen and (bucket["last_seen"] is None or seen > bucket["last_seen"]):
            bucket["last_seen"] = seen
    items = []
    for bucket in agg.values():
        n = bucket["executions"]
        items.append(
            {
                "name": bucket["name"],
                "executions": n,
                "failed_executions": bucket["failed"],
                "error_rate": round(bucket["failed"] / n, 4) if n else 0.0,
                "total_cost": money(bucket["cost"]),
                "total_tokens": bucket["tokens"],
                "avg_duration_ms": round(fmean(bucket["durations"]), 2)
                if bucket["durations"]
                else 0.0,
                "last_seen": bucket["last_seen"].isoformat() if bucket["last_seen"] else None,
            }
        )
    items.sort(key=lambda i: i["total_cost"] or 0, reverse=True)
    return {"items": items, "total": len(items)}