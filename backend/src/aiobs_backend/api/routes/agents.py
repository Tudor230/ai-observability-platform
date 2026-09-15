"""Agents: list of seen agents with associated execution-level aggregates."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...models import Execution, Project, Span
from ..deps import get_db, get_project_scope, require_role
from ..queries import default_range, parse_dt
from ..serialize import money

router = APIRouter(tags=["agents"], dependencies=[Depends(require_role("engineer", "sdm"))])


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
    scope = project_id or project_scope

    # Distinct (agent, execution) pairs first: an execution with several AGENT
    # spans of the same name must bill its cost/tokens only once (F25), and the
    # aggregation runs in SQL (F11).
    conditions = [
        Span.kind == "AGENT",
        Span.started_at >= start_dt,
        Span.started_at < end_dt,
    ]
    if scope:
        conditions.append(Project.project_id == scope)
    distinct = (
        select(
            Span.name.label("name"),
            Execution.id.label("execution_id"),
            Execution.status.label("status"),
            Execution.total_cost.label("total_cost"),
            Execution.total_tokens.label("total_tokens"),
            Execution.started_at.label("started_at"),
        )
        .join(Execution, Execution.id == Span.execution_id)
        .join(Project, Project.id == Execution.project_id)
        .where(*conditions)
        .distinct()
        .subquery()
    )

    stmt = select(
        distinct.c.name,
        func.count(distinct.c.execution_id).label("executions"),
        func.count().filter(distinct.c.status == "error").label("failed"),
        func.coalesce(func.sum(distinct.c.total_cost), 0).label("total_cost"),
        func.coalesce(func.sum(distinct.c.total_tokens), 0).label("total_tokens"),
        func.max(distinct.c.started_at).label("last_seen"),
    ).group_by(distinct.c.name)

    items = []
    for row in session.execute(stmt).all():
        n = row.executions
        items.append(
            {
                "name": row.name or "unknown",
                "executions": n,
                "failed_executions": row.failed,
                "error_rate": round(row.failed / n, 4) if n else 0.0,
                "total_cost": money(row.total_cost),
                "total_tokens": row.total_tokens,
                "last_seen": row.last_seen.isoformat() if row.last_seen else None,
            }
        )
    items.sort(key=lambda i: i["total_cost"] or 0, reverse=True)
    return {"items": items, "total": len(items)}
