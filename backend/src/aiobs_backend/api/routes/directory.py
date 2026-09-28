"""Directory: scoped project list plus departments/teams for filters and forms."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...models import Department, Project, ProjectKey, Team
from ..deps import AccessScope, get_db, require_access

router = APIRouter(tags=["directory"])


@router.get("/projects")
def list_visible_projects(
    access: AccessScope = Depends(require_access()),
    session: Session = Depends(get_db),
) -> dict:
    """Projects the caller may see, with team/department context and key status."""
    stmt = (
        select(Project, Team, Department)
        .join(Team, Team.id == Project.team_id)
        .join(Department, Department.id == Team.department_id)
        .order_by(Department.name, Team.name, Project.project_id)
    )
    if access.project_ids is not None:
        if not access.project_ids:
            return {"items": [], "total": 0}
        stmt = stmt.where(Project.project_id.in_(access.project_ids))
    rows = session.execute(stmt).all()
    active_keys: dict[str, int] = {
        project_db_id: count
        for project_db_id, count in session.execute(
            select(ProjectKey.project_id, func.count())
            .where(ProjectKey.revoked_at.is_(None))
            .group_by(ProjectKey.project_id)
        ).all()
    }
    items = [
        {
            "id": p.id,
            "project_id": p.project_id,
            "name": p.name,
            "enabled": p.enabled,
            "has_keys": active_keys.get(p.id, 0) > 0,
            "active_keys": active_keys.get(p.id, 0),
            "team_id": team.id,
            "team_name": team.name,
            "department_id": department.id,
            "department_name": department.name,
        }
        for p, team, department in rows
    ]
    return {"items": items, "total": len(items)}


@router.get("/departments")
def list_departments(
    access: AccessScope = Depends(require_access()),
    session: Session = Depends(get_db),
) -> dict:
    rows = session.execute(select(Department).order_by(Department.name)).scalars().all()
    items = [{"id": d.id, "name": d.name} for d in rows]
    return {"items": items, "total": len(items)}


@router.get("/teams")
def list_teams(
    access: AccessScope = Depends(require_access()),
    department_id: str | None = Query(default=None),
    session: Session = Depends(get_db),
) -> dict:
    stmt = (
        select(Team, Department)
        .join(Department, Department.id == Team.department_id)
        .order_by(Department.name, Team.name)
    )
    if department_id:
        stmt = stmt.where(Team.department_id == department_id)
    items = [
        {
            "id": team.id,
            "name": team.name,
            "department_id": department.id,
            "department_name": department.name,
        }
        for team, department in session.execute(stmt).all()
    ]
    return {"items": items, "total": len(items)}
