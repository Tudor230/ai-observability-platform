"""Projects: admin CRUD, scoped key management, and ingest-key lifecycle (ADR-0007)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...models import Department, Project, ProjectKey, Team
from ...security import generate_api_key, hash_api_key, key_hint
from ..deps import AccessScope, get_admin_key, get_db, require_access

router = APIRouter(tags=["projects"])


class ProjectIn(BaseModel):
    project_id: str = Field(min_length=2, max_length=120)
    name: str
    team_id: str | None = None
    # Legacy convenience: find-or-create a team inside a department.
    team_name: str = "Platform Admins"
    department_name: str = "Platform"


class KeyIn(BaseModel):
    label: str | None = Field(default=None, max_length=120)


class KeyOut(BaseModel):
    id: str
    project_id: str
    label: str | None = None
    api_key: str


def _find_or_create_team(
    session: Session, *, team_id: str | None, team_name: str, department_name: str
) -> Team:
    if team_id:
        team = session.get(Team, team_id)
        if team is None:
            raise HTTPException(status_code=404, detail="unknown team")
        return team
    team = session.execute(
        select(Team).where(Team.name == team_name)
    ).scalar_one_or_none()
    if team is not None:
        return team
    department = session.execute(
        select(Department).where(Department.name == department_name)
    ).scalar_one_or_none()
    if department is None:
        department = Department(name=department_name)
        session.add(department)
        session.flush()
    team = Team(name=team_name, department_id=department.id)
    session.add(team)
    session.flush()
    return team


def _mint_key(
    session: Session, project: Project, *, label: str | None, created_by: str | None
) -> tuple[ProjectKey, str]:
    api_key = generate_api_key()
    row = ProjectKey(
        project_id=project.id,
        key_hash=hash_api_key(api_key),
        key_hint=key_hint(api_key),
        label=label,
        created_by=created_by,
    )
    session.add(row)
    session.flush()
    return row, api_key


def _key_dict(row: ProjectKey) -> dict:
    return {
        "id": row.id,
        "label": row.label,
        "hint": f"••••{row.key_hint}" if row.key_hint else "••••",
        "active": row.revoked_at is None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
    }


def _project_row(session: Session, project_id: str) -> Project:
    project = session.execute(
        select(Project).where(Project.project_id == project_id)
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return project


def _require_manage(access: AccessScope, project: Project) -> None:
    if not access.unrestricted:
        access.ensure_visible(project.project_id, "project not found")


def _key_row(session: Session, project: Project, key_id: str) -> ProjectKey:
    row = session.execute(
        select(ProjectKey).where(
            ProjectKey.id == key_id, ProjectKey.project_id == project.id
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="key not found")
    return row


@router.get("/projects", dependencies=[Depends(get_admin_key)])
def list_projects(session: Session = Depends(get_db)) -> dict:
    rows = session.execute(select(Project).order_by(Project.created_at.desc())).scalars().all()
    key_counts: dict[str, int] = {
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
            "active_keys": key_counts.get(p.id, 0),
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in rows
    ]
    return {"items": items, "total": len(items)}


@router.post("/projects", response_model=KeyOut, dependencies=[Depends(get_admin_key)])
def create_project(body: ProjectIn, session: Session = Depends(get_db)) -> KeyOut:
    existing = session.execute(
        select(Project.id).where(Project.project_id == body.project_id)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="project_id already exists")
    team = _find_or_create_team(
        session,
        team_id=body.team_id,
        team_name=body.team_name,
        department_name=body.department_name,
    )
    project = Project(team_id=team.id, project_id=body.project_id, name=body.name)
    session.add(project)
    session.flush()
    row, api_key = _mint_key(
        session, project, label="admin-created", created_by=None
    )
    session.commit()  # before the response: see the ingest route note
    return KeyOut(id=row.id, project_id=body.project_id, label=row.label, api_key=api_key)


@router.get("/projects/{project_id}/keys")
def list_project_keys(
    project_id: str,
    access: AccessScope = Depends(require_access("engineer", "manager")),
    session: Session = Depends(get_db),
) -> dict:
    """All keys for a project: active first, then revoked (soft-deleted) rows."""
    project = _project_row(session, project_id)
    _require_manage(access, project)
    rows = session.execute(
        select(ProjectKey)
        .where(ProjectKey.project_id == project.id)
        .order_by(ProjectKey.revoked_at.is_not(None), ProjectKey.created_at.desc())
    ).scalars().all()
    return {"items": [_key_dict(row) for row in rows], "total": len(rows)}


@router.post("/projects/{project_id}/keys", response_model=KeyOut)
def create_project_key(
    project_id: str,
    body: KeyIn,
    access: AccessScope = Depends(require_access("engineer", "manager")),
    session: Session = Depends(get_db),
) -> KeyOut:
    """Add an ingest key; the plaintext is returned exactly once."""
    project = _project_row(session, project_id)
    _require_manage(access, project)
    row, api_key = _mint_key(
        session,
        project,
        label=(body.label or "").strip() or None,
        created_by=access.user.id if access.user else None,
    )
    session.commit()
    return KeyOut(id=row.id, project_id=project_id, label=row.label, api_key=api_key)


@router.post("/projects/{project_id}/keys/{key_id}/rotate", response_model=KeyOut)
def rotate_project_key(
    project_id: str,
    key_id: str,
    access: AccessScope = Depends(require_access("engineer", "manager")),
    session: Session = Depends(get_db),
) -> KeyOut:
    """Regenerate one key's secret in place (keeps its label and history)."""
    project = _project_row(session, project_id)
    _require_manage(access, project)
    row = _key_row(session, project, key_id)
    if row.revoked_at is not None:
        raise HTTPException(status_code=409, detail="key has been revoked")
    api_key = generate_api_key()
    row.key_hash = hash_api_key(api_key)
    row.key_hint = key_hint(api_key)
    session.flush()
    session.commit()
    return KeyOut(id=row.id, project_id=project_id, label=row.label, api_key=api_key)


@router.delete("/projects/{project_id}/keys/{key_id}")
def revoke_project_key(
    project_id: str,
    key_id: str,
    access: AccessScope = Depends(require_access("engineer", "manager")),
    session: Session = Depends(get_db),
) -> dict:
    """Soft-revoke a key: it stops authenticating but stays visible for audit."""
    project = _project_row(session, project_id)
    _require_manage(access, project)
    row = _key_row(session, project, key_id)
    if row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
        session.flush()
    session.commit()
    return {"id": row.id, "active": False}


def _set_enabled(session: Session, project_id: str, enabled: bool) -> dict:
    project = _project_row(session, project_id)
    project.enabled = enabled
    project.revoked_at = None if enabled else datetime.now(timezone.utc)
    session.flush()
    session.commit()
    return {
        "project_id": project.project_id,
        "enabled": project.enabled,
        "revoked_at": project.revoked_at.isoformat() if project.revoked_at else None,
    }


@router.post("/projects/{project_id}/disable", dependencies=[Depends(get_admin_key)])
def disable_project(project_id: str, session: Session = Depends(get_db)) -> dict:
    """Revoke a project's keys (F18): ingest answers 403 until re-enabled."""
    return _set_enabled(session, project_id, enabled=False)


@router.post("/projects/{project_id}/enable", dependencies=[Depends(get_admin_key)])
def enable_project(project_id: str, session: Session = Depends(get_db)) -> dict:
    return _set_enabled(session, project_id, enabled=True)
