"""Analytics rollup (plans/backend.md §9): recompute daily metrics per dimension.

Dimension keys are **external** identifiers: project `project_id`, client
`external_key`, workflow name — matching what the API and dashboard use.
"""
from __future__ import annotations

from datetime import datetime, timezone
from statistics import fmean

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Client, DailyMetric, Execution, Project

DIMENSIONS = ("total", "project", "client", "workflow")


def _day_key(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")


def rollup_metrics(session: Session, days: list[str] | None = None) -> dict[str, int]:
    """Recompute DailyMetric rows from executions for the given days (default: all)."""
    q = (
        select(Execution, Project.project_id, Client.external_key)
        .join(Project, Project.id == Execution.project_id)
        .outerjoin(Client, Client.id == Execution.client_id)
    )
    grouped: dict[tuple[str, str, str | None], list[Execution]] = {}
    seen_days: set[str] = set()
    for ex, project_ext, client_ext in session.execute(q):
        if ex.started_at is None:
            continue
        day = _day_key(ex.started_at)
        if days is not None and day not in days:
            continue
        seen_days.add(day)
        buckets = {
            "total": (day, "total", None),
            "project": (day, "project", project_ext),
            "client": (day, "client", client_ext),
            "workflow": (day, "workflow", ex.workflow_name),
        }
        for dim, key in buckets.items():
            grouped.setdefault(key, []).append(ex)

    session.query(DailyMetric).filter(
        DailyMetric.day.in_(sorted(seen_days))
    ).delete(synchronize_session=False)

    counts: dict[str, int] = {}
    for (day, dim, dim_key), group in grouped.items():
        executions = len(group)
        failed = sum(1 for e in group if e.status == "error")
        total_cost = sum(float(e.total_cost or 0) for e in group)
        tokens = sum(e.total_tokens for e in group)
        inp = sum(e.input_tokens for e in group)
        outp = sum(e.output_tokens for e in group)
        llm = sum(e.llm_calls for e in group)
        tools = sum(e.tool_calls for e in group)
        durations = [e.duration_ms for e in group if e.duration_ms is not None]
        avg_ms = fmean(durations) if durations else 0.0
        session.add(
            DailyMetric(
                day=day,
                dimension=dim,
                dimension_key=dim_key,
                executions=executions,
                failed_executions=failed,
                error_rate=round(failed / executions, 4) if executions else 0.0,
                total_tokens=tokens,
                input_tokens=inp,
                output_tokens=outp,
                llm_calls=llm,
                tool_calls=tools,
                total_cost=round(total_cost, 6),
                avg_duration_ms=round(avg_ms, 2),
            )
        )
        key = f"{day}:{dim}:{dim_key}"
        counts[key] = executions
    session.flush()
    return counts


def rollup_recent(session: Session, window_days: int = 90) -> dict[str, int]:
    """Recompute metrics for every day that has executions within the window."""
    from datetime import timedelta

    start = datetime.now(timezone.utc) - timedelta(days=window_days)
    days = {
        _day_key(e.started_at)
        for e in session.execute(select(Execution).where(Execution.started_at >= start)).scalars()
    }
    return rollup_metrics(session, list(days))