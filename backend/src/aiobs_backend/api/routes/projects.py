"""Projects (admin): register a project, mint/rotate/revoke API keys."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Project, Team
from ...security import generate_api_key, hash_api_key
from ..deps import get_admin_key, get_db

router = APIRouter(tags=["projects"], dependencies=[Depends(get_admin_key)])


class ProjectIn(BaseModel):
    project_id: str = Field(min_length=2, max_length=120)
    name: str
    team_name: str = "Platform Admins"


class KeyOut(BaseModel):
    project_id: str
    api_key: str


@router.get("/projects")
def list_projects(session: Session = Depends(get_db)) -> dict:
    rows = session.execute(select(Project).order_by(Project.created_at.desc())).scalars().all()
    items = [
        {
            "id": p.id,
            "project_id": p.project_id,
            "name": p.name,
            "enabled": p.enabled,
            "api_key_label": p.api_key_label,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in rows
    ]
    return {"items": items, "total": len(items)}


@router.post("/projects", response_model=KeyOut)
def create_project(body: ProjectIn, session: Session = Depends(get_db)) -> KeyOut:
    existing = session.execute(
        select(Project.id).where(Project.project_id == body.project_id)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="project_id already exists")
    team = session.execute(
        select(Team).where(Team.name == body.team_name)
    ).scalar_one_or_none()
    if team is None:
        team = Team(name=body.team_name)
        session.add(team)
        session.flush()
    key = generate_api_key()
    project = Project(
        team_id=team.id,
        project_id=body.project_id,
        name=body.name,
        api_key_hash=hash_api_key(key),
        api_key_label="admin-created",
    )
    session.add(project)
    session.flush()
    session.commit()  # before the response: see ingest route note
    return KeyOut(project_id=body.project_id, api_key=key)


@router.post("/projects/{project_id}/rotate")
def rotate_key(project_id: str, session: Session = Depends(get_db)) -> KeyOut:
    project = session.execute(
        select(Project).where(Project.project_id == project_id)
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    key = generate_api_key()
    project.api_key_hash = hash_api_key(key)
    session.flush()
    session.commit()
    return KeyOut(project_id=project_id, api_key=key)


def _set_enabled(session: Session, project_id: str, enabled: bool) -> dict:
    project = session.execute(
        select(Project).where(Project.project_id == project_id)
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    project.enabled = enabled
    project.revoked_at = None if enabled else datetime.now(timezone.utc)
    session.flush()
    session.commit()
    return {
        "project_id": project.project_id,
        "enabled": project.enabled,
        "revoked_at": project.revoked_at.isoformat() if project.revoked_at else None,
    }


@router.post("/projects/{project_id}/disable")
def disable_project(project_id: str, session: Session = Depends(get_db)) -> dict:
    """Revoke a project's keys (F18): ingest answers 403 until re-enabled."""
    return _set_enabled(session, project_id, enabled=False)


@router.post("/projects/{project_id}/enable")
def enable_project(project_id: str, session: Session = Depends(get_db)) -> dict:
    return _set_enabled(session, project_id, enabled=True)