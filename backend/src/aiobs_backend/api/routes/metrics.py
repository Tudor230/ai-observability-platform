"""Metrics: daily time-series from the analytics rollup."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import DailyMetric
from ..deps import get_db

router = APIRouter(tags=["metrics"])

DIMENSIONS = {"total", "project", "client", "workflow"}


@router.get("/metrics")
def get_metrics(
    session: Session = Depends(get_db),
    dimension: str = Query(default="total"),
    dimension_key: str | None = Query(default=None),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
) -> dict:
    if dimension not in DIMENSIONS:
        return {"items": [], "detail": f"dimension must be one of {sorted(DIMENSIONS)}"}
    stmt = select(DailyMetric).where(DailyMetric.dimension == dimension)
    if dimension_key is not None:
        stmt = stmt.where(DailyMetric.dimension_key == dimension_key)
    if start:
        stmt = stmt.where(DailyMetric.day >= start[:10])
    if end:
        stmt = stmt.where(DailyMetric.day <= end[:10])
    rows = session.execute(stmt.order_by(DailyMetric.day)).scalars().all()
    items = [
        {
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
        for m in rows
    ]
    return {"items": items, "total": len(items)}