"""Costs: aggregation by dimension over a time range."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Client, CostRecord, Execution, Project, Team
from ..deps import get_db, get_project_scope, require_role
from ..queries import default_range, exec_aggregates, parse_dt
from ..serialize import money

router = APIRouter(tags=["costs"], dependencies=[Depends(require_role("sdm", "finance"))])

DIMENSIONS = {"project", "client", "workflow", "model", "team"}

_GROUP_COLUMNS = {
    "project": Project.project_id,
    "client": Client.external_key,
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
    client_id: str | None = Query(default=None),
    workflow: str | None = Query(default=None),
    project_scope: str | None = Depends(get_project_scope),
) -> dict:
    if dimension not in DIMENSIONS:
        raise HTTPException(
            status_code=422, detail=f"dimension must be one of {sorted(DIMENSIONS)}"
        )
    end_dt = parse_dt(end, end_of_day=True) or default_range(days)[1]
    start_dt = parse_dt(start) or (end_dt - timedelta(days=days))
    project_id = project_id or project_scope

    if dimension == "model":
        stmt = (
            select(CostRecord, Execution.started_at)
            .join(Execution, Execution.id == CostRecord.execution_id)
            .where(Execution.started_at >= start_dt, Execution.started_at < end_dt)
        )
        if project_id or client_id or workflow:
            stmt = stmt.join(Project, Project.id == Execution.project_id)
            if project_id:
                stmt = stmt.where(Project.project_id == project_id)
            if workflow:
                stmt = stmt.where(Execution.workflow_name == workflow)
            if client_id:
                stmt = stmt.join(Client, Client.id == Execution.client_id).where(
                    Client.external_key == client_id
                )
        rows = session.execute(stmt).all()
        agg: dict[str, dict] = {}
        for record, _ in rows:
            key = f"{record.provider or 'unknown'}:{record.model or 'unknown'}"
            bucket = agg.setdefault(
                key, {"key": key, "provider": record.provider, "model": record.model, "total_cost": 0.0, "input_tokens": 0, "output_tokens": 0}
            )
            bucket["total_cost"] += float(record.amount or 0)
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
        project_id=project_id,
        client_id=client_id,
        workflow=workflow,
    )
    fallback_key = {"client": "unattributed", "team": "unassigned"}.get(
        dimension, "unknown"
    )
    agg = {}
    for row in rows:
        key = row.key or fallback_key
        bucket = agg.setdefault(
            key, {"key": key, "total_cost": 0.0, "tokens": 0, "executions": 0, "llm_calls": 0}
        )
        bucket["total_cost"] += float(row.total_cost or 0)
        bucket["tokens"] += row.total_tokens
        bucket["executions"] += row.executions
        bucket["llm_calls"] += row.llm_calls
    items = sorted(agg.values(), key=lambda i: i["total_cost"], reverse=True)
    for i in items:
        i["total_cost"] = money(i["total_cost"])
    return {"items": items, "total": len(items)}
