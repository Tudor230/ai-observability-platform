"""Shared query/filter helpers for the read API."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from ..models import Client, Execution, Project

EXTERNAL = (Execution, Project.project_id, Client.external_key)


def parse_dt(value: str | None, *, end_of_day: bool = False) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
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
    return stmt


def fetch_exec_rows(session: Session, **filters) -> list[tuple[Execution, str | None, str | None]]:
    return list(session.execute(exec_rows(session, **filters)))