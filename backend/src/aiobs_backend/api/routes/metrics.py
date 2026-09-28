"""Metrics: daily time-series from the analytics rollup (scope-aware)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import DailyMetric
from ..deps import AccessScope, get_db, require_access

router = APIRouter(tags=["metrics"])

DIMENSIONS = {"total", "project", "client", "workflow", "team"}
_SUMMED_FIELDS = (
    "executions",
    "failed_executions",
    "total_tokens",
    "input_tokens",
    "output_tokens",
    "llm_calls",
    "tool_calls",
    "total_cost",
)
_AVERAGED_FIELDS = (
    "avg_duration_ms",
    "p50_duration_ms",
    "p95_duration_ms",
    "p99_duration_ms",
)


def _metric_dict(m: DailyMetric) -> dict:
    return {
        "day": m.day,
        "dimension": m.dimension,
        "dimension_key": m.dimension_key,
        "executions": m.executions,
        "failed_executions": m.failed_executions,
        "error_rate": float(m.error_rate or 0),
        "total_tokens": m.total_tokens,
        "input_tokens": m.input_tokens,
        "output_tokens": m.output_tokens,
        "llm_calls": m.llm_calls,
        "tool_calls": m.tool_calls,
        "total_cost": float(m.total_cost or 0),
        "avg_duration_ms": float(m.avg_duration_ms or 0),
        "p50_duration_ms": float(m.p50_duration_ms or 0),
        "p95_duration_ms": float(m.p95_duration_ms or 0),
        "p99_duration_ms": float(m.p99_duration_ms or 0),
    }


def _scoped_totals(
    session: Session, project_ids: frozenset[str], start: str | None, end: str | None
) -> list[dict]:
    """Aggregate the allowed projects' daily rows into a total series.

    Duration percentiles are execution-weighted approximations across projects
    (the ``total`` rollup row is global and must not leak to scoped callers).
    """
    stmt = select(DailyMetric).where(
        DailyMetric.dimension == "project",
        DailyMetric.dimension_key.in_(project_ids),
    )
    if start:
        stmt = stmt.where(DailyMetric.day >= start[:10])
    if end:
        stmt = stmt.where(DailyMetric.day <= end[:10])
    rows = session.execute(stmt.order_by(DailyMetric.day)).scalars().all()

    grouped: dict[str, dict] = {}
    for m in rows:
        bucket = grouped.get(m.day)
        if bucket is None:
            bucket = {field: 0.0 for field in _SUMMED_FIELDS + _AVERAGED_FIELDS}
            bucket.update({"day": m.day, "dimension": "total", "dimension_key": None})
            grouped[m.day] = bucket
        for field in _SUMMED_FIELDS:
            bucket[field] += float(getattr(m, field) or 0)
        weight = max(m.executions, 1)
        for field in _AVERAGED_FIELDS:
            bucket[field] += float(getattr(m, field) or 0) * weight
        bucket["_weight"] = bucket.get("_weight", 0) + weight

    items = []
    for day in sorted(grouped):
        bucket = grouped.pop(day)
        weight = bucket.pop("_weight", 0) or 1
        for field in _AVERAGED_FIELDS:
            bucket[field] = round(bucket[field] / weight, 2)
        bucket["error_rate"] = (
            round(bucket["failed_executions"] / bucket["executions"], 4)
            if bucket["executions"]
            else 0.0
        )
        items.append(bucket)
    return items


@router.get("/metrics")
def get_metrics(
    session: Session = Depends(get_db),
    dimension: str = Query(default="total"),
    dimension_key: str | None = Query(default=None),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    days: int | None = Query(default=None, ge=1, le=3650),
    access: AccessScope = Depends(require_access()),
) -> dict:
    if dimension not in DIMENSIONS:
        raise HTTPException(
            status_code=422, detail=f"dimension must be one of {sorted(DIMENSIONS)}"
        )
    # The validated `x-project-name` header, folded into the allowed set.
    scope_ids = access.resolve_project_filter(None)
    if days is not None and not start:
        start = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()

    if dimension == "total" and scope_ids is not None:
        # A scoped caller asking for "total" gets the sum of their projects (F07).
        items = _scoped_totals(session, scope_ids, start, end)
        return {"items": items, "total": len(items)}

    if dimension in {"client", "workflow", "team"} and scope_ids is not None:
        raise HTTPException(
            status_code=403,
            detail=f"dimension {dimension!r} is not available at this scope",
        )

    stmt = select(DailyMetric).where(DailyMetric.dimension == dimension)
    if dimension == "project" and scope_ids is not None:
        if dimension_key is not None and dimension_key not in scope_ids:
            raise HTTPException(status_code=404, detail=f"unknown project {dimension_key}")
        stmt = stmt.where(DailyMetric.dimension_key.in_(scope_ids))
    if dimension_key is not None:
        stmt = stmt.where(DailyMetric.dimension_key == dimension_key)
    if start:
        stmt = stmt.where(DailyMetric.day >= start[:10])
    if end:
        stmt = stmt.where(DailyMetric.day <= end[:10])
    rows = session.execute(stmt.order_by(DailyMetric.day)).scalars().all()
    items = [_metric_dict(m) for m in rows]
    return {"items": items, "total": len(items)}
