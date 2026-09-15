"""Shared query/filter helpers for the read API."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from ..models import Client, Execution, Project, Team

EXTERNAL = (Execution, Project.project_id, Client.external_key)


def parse_dt(value: str | None, *, end_of_day: bool = False) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            dt = datetime.strptime(value, fmt)
        except ValueError:
            continue
        # Naive inputs are interpreted as UTC (F31), never as server-local time.
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    try:
        d = date.fromisoformat(value)
    except ValueError:
        return None
    t = time.max if end_of_day else time.min
    return datetime.combine(d, t, tzinfo=timezone.utc)


def default_range(days: int = 30) -> tuple[datetime, datetime]:
    end = datetime.now(timezone.utc)
    return (end - timedelta(days=days), end)


def exec_rows(
    session: Session,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    project_id: str | None = None,
    client_id: str | None = None,
    workflow: str | None = None,
    status: str | None = None,
) -> Select:
    """Select (Execution, project_ext, client_ext) with the given filters applied."""
    stmt = select(*EXTERNAL).join(Project, Project.id == Execution.project_id).outerjoin(
        Client, Client.id == Execution.client_id
    )
    if start:
        stmt = stmt.where(Execution.started_at >= start)
    if end:
        stmt = stmt.where(Execution.started_at < end)
    if project_id:
        stmt = stmt.where(Project.project_id == project_id)
    if client_id:
        stmt = stmt.where(Client.external_key == client_id)
    if workflow:
        stmt = stmt.where(Execution.workflow_name == workflow)
    if status:
        stmt = stmt.where(Execution.status == status)
    # Stable ordering for pagination and every aggregate consumer (F11).
    return stmt.order_by(Execution.started_at.desc(), Execution.id.desc())


def fetch_exec_rows(session: Session, **filters) -> list[tuple[Execution, str | None, str | None]]:
    rows = session.execute(exec_rows(session, **filters)).all()
    return [(row[0], row[1], row[2]) for row in rows]


def exec_aggregates(
    session: Session,
    *,
    group_col,
    start: datetime | None = None,
    end: datetime | None = None,
    project_id: str | None = None,
    client_id: str | None = None,
    workflow: str | None = None,
):
    """Aggregate executions in SQL per dimension (F11).

    Returns rows with: key, executions, failed, total_cost, total_tokens,
    llm_calls, avg_duration_ms, last_seen.
    """
    stmt = (
        select(
            group_col.label("key"),
            func.count(Execution.id).label("executions"),
            func.count().filter(Execution.status == "error").label("failed"),
            func.coalesce(func.sum(Execution.total_cost), 0).label("total_cost"),
            func.coalesce(func.sum(Execution.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(Execution.llm_calls), 0).label("llm_calls"),
            func.coalesce(func.avg(Execution.duration_ms), 0).label("avg_duration_ms"),
            func.max(Execution.started_at).label("last_seen"),
        )
        .join(Project, Project.id == Execution.project_id)
        .join(Team, Team.id == Project.team_id)
        .outerjoin(Client, Client.id == Execution.client_id)
        .group_by(group_col)
    )
    if start:
        stmt = stmt.where(Execution.started_at >= start)
    if end:
        stmt = stmt.where(Execution.started_at < end)
    if project_id:
        stmt = stmt.where(Project.project_id == project_id)
    if client_id:
        stmt = stmt.where(Client.external_key == client_id)
    if workflow:
        stmt = stmt.where(Execution.workflow_name == workflow)
    return list(session.execute(stmt))