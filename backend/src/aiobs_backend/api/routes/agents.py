"""Agents: list of seen agents with associated execution-level aggregates."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Execution, Project, Span
from ..deps import get_db, get_project_scope, require_read_access
from ..queries import default_range, parse_dt
from ..serialize import money

router = APIRouter(tags=["agents"], dependencies=[Depends(require_read_access)])


@router.get("/agents")
def list_agents(
    session: Session = Depends(get_db),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    days: int = Query(default=90, ge=1, le=3650),
    project_id: str | None = Query(default=None),
    project_scope: str | None = Depends(get_project_scope),
) -> dict:
    end_dt = parse_dt(end, end_of_day=True) or default_range(days)[1]
    start_dt = parse_dt(start) or (end_dt - timedelta(days=days))
    stmt = (
        select(Span, Execution)
        .join(Execution, Execution.id == Span.execution_id)
        .join(Project, Project.id == Execution.project_id)
        .where(Span.kind == "AGENT", Span.started_at >= start_dt, Span.started_at < end_dt)
    )
    scope = project_id or project_scope
    if scope:
        stmt = stmt.where(Project.project_id == scope)
    rows = session.execute(stmt).all()
    agg: dict[str, dict] = {}
    for span, ex in rows:
        name = span.name or "unknown"
        bucket = agg.setdefault(
            name,
            {"name": name, "executions": set(), "failed": 0, "cost": 0.0, "tokens": 0, "last_seen": None},
        )
        bucket["executions"].add(ex.id)
        if ex.status == "error":
            bucket["failed"] += 1
        bucket["cost"] += float(ex.total_cost or 0)
        bucket["tokens"] += ex.total_tokens
        seen = ex.started_at
        if seen and (bucket["last_seen"] is None or seen > bucket["last_seen"]):
            bucket["last_seen"] = seen
    items = []
    for bucket in agg.values():
        n = len(bucket["executions"])
        items.append(
            {
                "name": bucket["name"],
                "executions": n,
                "failed_executions": bucket["failed"],
                "error_rate": round(bucket["failed"] / n, 4) if n else 0.0,
                "total_cost": money(bucket["cost"]),
                "total_tokens": bucket["tokens"],
                "last_seen": bucket["last_seen"].isoformat() if bucket["last_seen"] else None,
            }
        )
    items.sort(key=lambda i: i["total_cost"] or 0, reverse=True)
    return {"items": items, "total": len(items)}