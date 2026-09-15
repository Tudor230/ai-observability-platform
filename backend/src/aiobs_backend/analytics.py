"""Analytics rollup (plans/backend.md §9): recompute daily metrics per dimension.

Dimension keys are **external** identifiers: project `project_id`, client
`external_key`, workflow name, team name — matching what the API and dashboard
use. Writes are upserts against the `uq_daily_dim` constraint so concurrent
rollups cannot create duplicate metric rows (F26).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from statistics import fmean

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from .models import Client, DailyMetric, Execution, Project, Team
from .stats import percentile

DIMENSIONS = ("total", "project", "client", "workflow", "team")

_UPSERT_COLUMNS = (
    "executions",
    "failed_executions",
    "error_rate",
    "total_tokens",
    "input_tokens",
    "output_tokens",
    "llm_calls",
    "tool_calls",
    "total_cost",
    "avg_duration_ms",
    "p50_duration_ms",
    "p95_duration_ms",
    "p99_duration_ms",
)


def _day_key(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")


def rollup_metrics(session: Session, days: list[str] | None = None) -> dict[str, int]:
    """Recompute DailyMetric rows from executions for the given days (default: all)."""
    q = (
        select(Execution, Project.project_id, Client.external_key, Team.name)
        .join(Project, Project.id == Execution.project_id)
        .join(Team, Team.id == Project.team_id)
        .outerjoin(Client, Client.id == Execution.client_id)
    )
    grouped: dict[tuple[str, str, str | None], list[Execution]] = {}
    seen_days: set[str] = set()
    for ex, project_ext, client_ext, team_name in session.execute(q):
        if ex.started_at is None:
            continue
        day = _day_key(ex.started_at)
        if days is not None and day not in days:
            continue
        seen_days.add(day)
        buckets = {
            "total": (day, "total", None),
            "project": (day, "project", project_ext),
            "team": (day, "team", team_name),
            "client": (day, "client", client_ext),
            "workflow": (day, "workflow", ex.workflow_name),
        }
        for key in buckets.values():
            grouped.setdefault(key, []).append(ex)

    session.query(DailyMetric).filter(
        DailyMetric.day.in_(sorted(seen_days))
    ).delete(synchronize_session=False)

    rows: list[dict] = []
    counts: dict[str, int] = {}
    for (day, dim, dim_key), group in grouped.items():
        executions = len(group)
        failed = sum(1 for e in group if e.status == "error")
        total_cost = sum(
            (e.total_cost or Decimal("0") for e in group), Decimal("0")
        )
        tokens = sum(e.total_tokens for e in group)
        inp = sum(e.input_tokens for e in group)
        outp = sum(e.output_tokens for e in group)
        llm = sum(e.llm_calls for e in group)
        tools = sum(e.tool_calls for e in group)
        durations = [e.duration_ms for e in group if e.duration_ms is not None]
        avg_ms = fmean(durations) if durations else 0.0
        rows.append(
            {
                "id": uuid.uuid4().hex,
                "day": day,
                "dimension": dim,
                "dimension_key": dim_key,
                "executions": executions,
                "failed_executions": failed,
                "error_rate": round(failed / executions, 4) if executions else 0.0,
                "total_tokens": tokens,
                "input_tokens": inp,
                "output_tokens": outp,
                "llm_calls": llm,
                "tool_calls": tools,
                "total_cost": round(total_cost, 6),
                "avg_duration_ms": round(avg_ms, 2),
                "p50_duration_ms": round(percentile(durations, 0.5), 2),
                "p95_duration_ms": round(percentile(durations, 0.95), 2),
                "p99_duration_ms": round(percentile(durations, 0.99), 2),
            }
        )
        counts[f"{day}:{dim}:{dim_key}"] = executions

    if rows:
        stmt = pg_insert(DailyMetric).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_daily_dim",
            set_={col: stmt.excluded[col] for col in _UPSERT_COLUMNS},
        )
        session.execute(stmt)
    session.flush()
    return counts


def rollup_recent(session: Session, window_days: int = 90) -> dict[str, int]:
    """Recompute metrics for every day that has executions within the window."""
    from datetime import timedelta

    start = datetime.now(timezone.utc) - timedelta(days=window_days)
    days = {
        _day_key(e.started_at)
        for e in session.execute(
            select(Execution).where(Execution.started_at >= start)
        ).scalars()
    }
    return rollup_metrics(session, list(days))
