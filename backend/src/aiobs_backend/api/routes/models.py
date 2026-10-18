"""Model insights: per provider·model economics (Phoenix "Model Insights").

Cost and tokens come from the billing ``cost_records`` rows (the resolved
pricing snapshot, so history survives pricing edits); calls, failures and
latency come from the LLM spans. The two are merged on the ``provider:model``
key, which mirrors the ``/costs?dimension=model`` key format.
"""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...models import CostRecord, Execution, Project, Span
from ...stats import percentile
from ..deps import AccessScope, get_db, require_access
from ..queries import default_range, parse_dt
from ..serialize import money

router = APIRouter(tags=["models"])

UNKNOWN = "unknown"


def _key(provider: str | None, model: str | None) -> str:
    return f"{provider or UNKNOWN}:{model or UNKNOWN}"


@router.get("/models")
def list_models(
    session: Session = Depends(get_db),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    days: int = Query(default=90, ge=1, le=3650),
    project_id: str | None = Query(default=None),
    workflow: str | None = Query(default=None),
    access: AccessScope = Depends(require_access("manager", "exec")),
) -> dict:
    end_dt = parse_dt(end, end_of_day=True) or default_range(days)[1]
    start_dt = parse_dt(start) or (end_dt - timedelta(days=days))
    project_ids = access.resolve_project_filter(project_id)

    buckets: dict[str, dict] = {}

    def bucket(provider: str | None, model: str | None) -> dict:
        return buckets.setdefault(
            _key(provider, model),
            {
                "key": _key(provider, model),
                "provider": provider,
                "model": model,
                "calls": 0,
                "failed_calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_cost": 0.0,
                "_durations": [],
                "_executions": set(),
                "_last_seen": None,
            },
        )

    # Calls, failures and latency: the LLM spans in the window.
    span_stmt = (
        select(
            Span.llm_provider,
            Span.llm_model,
            Span.duration_ms,
            Span.status,
            Execution.id,
            Execution.started_at,
        )
        .join(Execution, Execution.id == Span.execution_id)
        .join(Project, Project.id == Execution.project_id)
        .where(
            Span.kind == "LLM",
            Span.started_at >= start_dt,
            Span.started_at < end_dt,
        )
    )
    if project_ids is not None:
        span_stmt = span_stmt.where(Project.project_id.in_(project_ids))
    if workflow:
        span_stmt = span_stmt.where(Execution.workflow_name == workflow)
    for provider, model, duration, status, execution_id, started_at in session.execute(
        span_stmt
    ).all():
        item = bucket(provider, model)
        item["calls"] += 1
        if status == "error":
            item["failed_calls"] += 1
        if duration is not None:
            item["_durations"].append(float(duration))
        item["_executions"].add(execution_id)
        if item["_last_seen"] is None or started_at > item["_last_seen"]:
            item["_last_seen"] = started_at

    # Cost and tokens: the billing rows for the same window.
    cost_stmt = (
        select(
            CostRecord.provider,
            CostRecord.model,
            func.coalesce(func.sum(CostRecord.input_tokens), 0),
            func.coalesce(func.sum(CostRecord.output_tokens), 0),
            func.coalesce(func.sum(CostRecord.amount), 0),
        )
        .join(Execution, Execution.id == CostRecord.execution_id)
        .join(Project, Project.id == Execution.project_id)
        .where(Execution.started_at >= start_dt, Execution.started_at < end_dt)
        .group_by(CostRecord.provider, CostRecord.model)
    )
    if project_ids is not None:
        cost_stmt = cost_stmt.where(Project.project_id.in_(project_ids))
    if workflow:
        cost_stmt = cost_stmt.where(Execution.workflow_name == workflow)
    for provider, model, input_tokens, output_tokens, amount in session.execute(
        cost_stmt
    ).all():
        item = bucket(provider, model)
        item["input_tokens"] += int(input_tokens or 0)
        item["output_tokens"] += int(output_tokens or 0)
        item["total_cost"] += float(amount or 0)

    items = []
    for item in buckets.values():
        durations = item.pop("_durations")
        executions = item.pop("_executions")
        last_seen = item.pop("_last_seen")
        calls = item["calls"]
        item["executions"] = len(executions)
        item["error_rate"] = round(item["failed_calls"] / calls, 4) if calls else 0.0
        item["total_tokens"] = item["input_tokens"] + item["output_tokens"]
        item["avg_duration_ms"] = (
            round(sum(durations) / len(durations), 2) if durations else 0.0
        )
        item["p95_duration_ms"] = round(percentile(durations, 0.95), 2)
        item["total_cost"] = money(item["total_cost"])
        item["last_seen"] = last_seen.isoformat() if last_seen else None
        items.append(item)
    items.sort(key=lambda i: (i.get("total_cost") or 0, i["calls"]), reverse=True)
    return {"items": items, "total": len(items)}
