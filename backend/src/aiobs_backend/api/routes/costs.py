"""Costs: aggregation by dimension over a time range."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import CostRecord, Execution, Project, Team
from ..deps import AccessScope, get_db, require_access
from ..queries import default_range, exec_aggregates, parse_dt
from ..serialize import money

router = APIRouter(tags=["costs"])

DIMENSIONS = {"project", "workflow", "model", "team"}

_GROUP_COLUMNS = {
    "project": Project.project_id,
    "workflow": Execution.workflow_name,
    "team": Team.name,
}


@router.get("/costs")
def get_costs(
    session: Session = Depends(get_db),
    dimension: str = Query(default="project"),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    days: int = Query(default=90, ge=1, le=3650),
    project_id: str | None = Query(default=None),
    workflow: str | None = Query(default=None),
    access: AccessScope = Depends(require_access("manager", "exec")),
) -> dict:
    """Cost/usage rollup per dimension.

    ``dimension=model`` reads historical ``cost_records`` rows (cost + tokens
    only); every other dimension aggregates executions and returns the rich row
    shape the dashboard's detail views use: ``key``, ``total_cost``, ``tokens``
    (alias kept for existing charts), ``total_tokens``, ``executions``,
    ``failed_executions``, ``error_rate``, ``llm_calls``, ``avg_duration_ms``,
    ``last_seen``. Client-only callers cannot reach this route at all
    (`manager`/`exec` gate), so no cost stripping is needed here.
    """
    if dimension not in DIMENSIONS:
        raise HTTPException(
            status_code=422, detail=f"dimension must be one of {sorted(DIMENSIONS)}"
        )
    end_dt = parse_dt(end, end_of_day=True) or default_range(days)[1]
    start_dt = parse_dt(start) or (end_dt - timedelta(days=days))
    project_ids = access.resolve_project_filter(project_id)

    if dimension == "model":
        stmt = (
            select(CostRecord, Execution.started_at)
            .join(Execution, Execution.id == CostRecord.execution_id)
            .where(Execution.started_at >= start_dt, Execution.started_at < end_dt)
        )
        if project_ids is not None or workflow:
            stmt = stmt.join(Project, Project.id == Execution.project_id)
            if project_ids is not None:
                stmt = stmt.where(Project.project_id.in_(project_ids))
            if workflow:
                stmt = stmt.where(Execution.workflow_name == workflow)
        rows = session.execute(stmt).all()
        agg: dict[str, dict] = {}
        for record, _ in rows:
            key = f"{record.provider or 'unknown'}:{record.model or 'unknown'}"
            bucket = agg.setdefault(
                key, {"key": key, "provider": record.provider, "model": record.model, "total_cost": Decimal("0"), "input_tokens": 0, "output_tokens": 0}
            )
            bucket["total_cost"] += record.amount or Decimal("0")
            bucket["input_tokens"] += record.input_tokens
            bucket["output_tokens"] += record.output_tokens
        items = sorted(agg.values(), key=lambda i: i["total_cost"], reverse=True)
        for i in items:
            i["total_cost"] = money(i["total_cost"])
        return {"items": items, "total": len(items)}

    rows = exec_aggregates(
        session,
        group_col=_GROUP_COLUMNS[dimension],
        start=start_dt,
        end=end_dt,
        project_ids=project_ids,
        workflow=workflow,
    )
    fallback_key = {"team": "unassigned"}.get(dimension, "unknown")
    agg = {}
    for row in rows:
        key = row.key or fallback_key
        bucket = agg.setdefault(
            key,
            {
                "key": key,
                "total_cost": Decimal("0"),
                "tokens": 0,
                "total_tokens": 0,
                "executions": 0,
                "failed_executions": 0,
                "llm_calls": 0,
                "avg_duration_ms": 0.0,
                "last_seen": None,
            },
        )
        bucket["total_cost"] += row.total_cost or Decimal("0")
        bucket["tokens"] += row.total_tokens
        bucket["total_tokens"] += row.total_tokens
        bucket["executions"] += row.executions
        bucket["failed_executions"] += row.failed
        bucket["llm_calls"] += row.llm_calls
        bucket["avg_duration_ms"] = round(float(row.avg_duration_ms or 0), 2)
        last = row.last_seen.isoformat() if row.last_seen else None
        if last and (bucket["last_seen"] is None or last > bucket["last_seen"]):
            bucket["last_seen"] = last
    items = sorted(agg.values(), key=lambda i: i["total_cost"], reverse=True)
    for i in items:
        i["total_cost"] = money(i["total_cost"])
        n = i["executions"]
        i["error_rate"] = round(i["failed_executions"] / n, 4) if n else 0.0
    return {"items": items, "total": len(items)}
