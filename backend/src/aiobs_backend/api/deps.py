"""Shared FastAPI dependencies: DB session and auth guards."""
from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import session_scope
from ..models import Project
from ..security import verify_api_key


def get_db() -> Iterator[Session]:
    with session_scope() as session:
        yield session


def get_admin_key(x_admin_key: str | None = Header(default=None)) -> str:
    expected = get_settings().admin_api_key
    if not expected:
        raise HTTPException(status_code=503, detail="admin API not configured")
    if x_admin_key != expected:
        raise HTTPException(status_code=401, detail="invalid admin key")
    return x_admin_key


def get_project_from_headers(
    session: Session = Depends(get_db),
    x_project_name: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> Project:
    """Validate the SDK ingest headers: `x-project-name` + `authorization: Bearer <key>`."""
    if not x_project_name:
        raise HTTPException(status_code=401, detail="missing x-project-name header")
    project = session.execute(
        select(Project).where(Project.project_id == x_project_name)
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="unknown project")
    if not project.enabled:
        raise HTTPException(status_code=403, detail="project disabled")
    key = ""
    if authorization and authorization.lower().startswith("bearer "):
        key = authorization[7:]
    if not verify_api_key(key, project.api_key_hash):
        raise HTTPException(status_code=401, detail="invalid API key")
    return project


def get_project_scope(x_project_name: str | None = Header(default=None)) -> str | None:
    """Optional project scope for read endpoints (``x-project-name`` header).

    When present, responses are restricted to that project. No auth is required
    for reads in v1 (docs scope, plans §11.2).
    """
    return x_project_name