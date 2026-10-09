"""Shared query/filter helpers for the read API."""
from __future__ import annotations

from collections.abc import Collection
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import Select, and_, asc, desc, false, func, or_, select
from sqlalchemy.orm import Session

from ..models import Alert, Budget, Client, Execution, Project, Team

EXTERNAL = (Execution, Project.project_id, Client.external_key)

# Whitelisted sort keys for `GET /executions` (audit item 4).
EXECUTION_SORTS = {
    "started_at": Execution.started_at,
    "duration_ms": Execution.duration_ms,
    "total_cost": Execution.total_cost,
    "total_tokens": Execution.total_tokens,
    "error_count": Execution.error_count,
    "status": Execution.status,
}


def _project_scope_clause(project_ids: Collection[str] | None):
    """Filter clause for an allowed-project set; ``None`` means unrestricted."""
    if project_ids is None:
        return None
    return Project.project_id.in_(project_ids)


def alert_scope_clause(project_ids: Collection[str] | None):
    """Clause selecting alerts visible to a scoped caller.

    Rule alerts are global (exec/admin only); budget alerts follow the budget's
    project, so they can be attributed to a team scope (plans/roles.md §6.3).
    """
    if project_ids is None:
        return None
    if not project_ids:
        return false()
    allowed = select(Project.id).where(Project.project_id.in_(project_ids))
    return and_(Alert.dimension == "budget", Alert.dimension_key.in_(allowed))


def budget_scope_clause(
    project_ids: Collection[str] | None,
    department_ids: Collection[str] = (),
    team_ids: Collection[str] = (),
):
    """Clause selecting budgets visible to a scoped caller (global ones excluded).

    A budget is visible when its project, team or department scope intersects
    the caller's allowed set; global budgets (all scope fields NULL) return
    only for unrestricted callers.
    """
    if project_ids is None:
        return None
    clauses = []
    if project_ids:
        allowed = select(Project.id).where(Project.project_id.in_(project_ids))
        clauses.append(Budget.project_id.in_(allowed))
    if team_ids:
        clauses.append(Budget.team_id.in_(team_ids))
    if department_ids:
        clauses.append(Budget.department_id.in_(department_ids))
    if not clauses:
        return false()
    return or_(*clauses)


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
    project_ids: Collection[str] | None = None,
    client_id: str | None = None,
    workflow: str | None = None,
    status: str | None = None,
    q: str | None = None,
    sort: str | None = None,
    order: str | None = None,
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
    scope_clause = _project_scope_clause(project_ids)
    if scope_clause is not None:
        stmt = stmt.where(scope_clause)
    if client_id:
        stmt = stmt.where(Client.external_key == client_id)
    if workflow:
        stmt = stmt.where(Execution.workflow_name == workflow)
    if status:
        stmt = stmt.where(Execution.status == status)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(
                Execution.trace_id.ilike(pattern),
                Execution.workflow_name.ilike(pattern),
                Execution.root_error_message.ilike(pattern),
            )
        )
    # Stable ordering for pagination and every aggregate consumer (F11).
    # The whitelisted sort key is validated by the route; unknown values fall
    # back to the default instead of raising here.
    sort_col = EXECUTION_SORTS.get(sort or "started_at", Execution.started_at)
    order_fn = desc if (order or "desc").lower() == "desc" else asc
    return stmt.order_by(order_fn(sort_col), order_fn(Execution.id))


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
    project_ids: Collection[str] | None = None,
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
    scope_clause = _project_scope_clause(project_ids)
    if scope_clause is not None:
        stmt = stmt.where(scope_clause)
    if client_id:
        stmt = stmt.where(Client.external_key == client_id)
    if workflow:
        stmt = stmt.where(Execution.workflow_name == workflow)
    return list(session.execute(stmt))