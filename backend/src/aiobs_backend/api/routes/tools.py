"""Tool insights: per-tool call volume, failures and latency (Phoenix "Tools").

TOOL spans carry the resolved tool name (`spans.tool_name`, with the span name
as a fallback); failures are the spans that ended in error.
"""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Execution, Project, Span
from ...stats import percentile
from ..deps import AccessScope, get_db, require_access
from ..queries import default_range, parse_dt

router = APIRouter(tags=["tools"])


@router.get("/tools")
def list_tools(
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

    stmt = (
        select(
            Span.tool_name,
            Span.name,
            Span.duration_ms,
            Span.status,
            Execution.id,
            Execution.started_at,
        )
        .join(Execution, Execution.id == Span.execution_id)
        .join(Project, Project.id == Execution.project_id)
        .where(
            Span.kind == "TOOL",
            Span.started_at >= start_dt,
            Span.started_at < end_dt,
        )
    )
    if project_ids is not None:
        stmt = stmt.where(Project.project_id.in_(project_ids))
    if workflow:
        stmt = stmt.where(Execution.workflow_name == workflow)

    buckets: dict[str, dict] = {}
    for tool_name, span_name, duration, status, execution_id, started_at in session.execute(
        stmt
    ).all():
        name = tool_name or span_name or "unknown"
        item = buckets.setdefault(
            name,
            {
                "name": name,
                "calls": 0,
                "failed_calls": 0,
                "_durations": [],
                "_executions": set(),
                "_last_seen": None,
            },
        )
        item["calls"] += 1
        if status == "error":
            item["failed_calls"] += 1
        if duration is not None:
            item["_durations"].append(float(duration))
        item["_executions"].add(execution_id)
        if item["_last_seen"] is None or started_at > item["_last_seen"]:
            item["_last_seen"] = started_at

    items = []
    for item in buckets.values():
        durations = item.pop("_durations")
        executions = item.pop("_executions")
        last_seen = item.pop("_last_seen")
        calls = item["calls"]
        item["executions"] = len(executions)
        item["error_rate"] = round(item["failed_calls"] / calls, 4) if calls else 0.0
        item["avg_duration_ms"] = (
            round(sum(durations) / len(durations), 2) if durations else 0.0
        )
        item["p95_duration_ms"] = round(percentile(durations, 0.95), 2)
        item["last_seen"] = last_seen.isoformat() if last_seen else None
        items.append(item)
    items.sort(key=lambda i: (i["calls"], i["name"]), reverse=True)
    return {"items": items, "total": len(items)}
