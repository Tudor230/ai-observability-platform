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
    # Aggregate once per execution: an execution with several AGENT spans must
    # not bill its full cost/tokens once per span (F25).
    per_agent: dict[str, dict[str, Execution]] = {}
    for span, ex in rows:
        per_agent.setdefault(span.name or "unknown", {})[ex.id] = ex

    items = []
    for name, execs in per_agent.items():
        n = len(execs)
        failed = sum(1 for e in execs.values() if e.status == "error")
        cost = sum(float(e.total_cost or 0) for e in execs.values())
        tokens = sum(e.total_tokens for e in execs.values())
        last_seen = max(
            (e.started_at for e in execs.values() if e.started_at), default=None
        )
        items.append(
            {
                "name": name,
                "executions": n,
                "failed_executions": failed,
                "error_rate": round(failed / n, 4) if n else 0.0,
                "total_cost": money(cost),
                "total_tokens": tokens,
                "last_seen": last_seen.isoformat() if last_seen else None,
            }
        )
    items.sort(key=lambda i: i["total_cost"] or 0, reverse=True)
    return {"items": items, "total": len(items)}