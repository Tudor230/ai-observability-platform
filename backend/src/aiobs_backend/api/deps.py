"""Shared FastAPI dependencies: DB session and auth guards."""
from __future__ import annotations

import hmac
from collections.abc import Iterator

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import session_scope
from ..models import Project, User
from ..security import hash_api_key, verify_api_key


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


def get_project_scope(
    x_project_name: str | None = Header(default=None),
    session: Session = Depends(get_db),
) -> str | None:
    """Optional project scope for read endpoints (``x-project-name`` header).

    When present the value is validated against registered projects, so an
    unknown scope is rejected instead of silently returning global data (F07).
    """
    if not x_project_name:
        return None
    exists = session.execute(
        select(Project.id).where(Project.project_id == x_project_name)
    ).first()
    if exists is None:
        raise HTTPException(status_code=404, detail=f"unknown project {x_project_name}")
    return x_project_name


def require_read_access(
    x_api_key: str | None = Header(default=None),
    x_admin_key: str | None = Header(default=None),
) -> None:
    """Read authentication (F06), enforced when ``AIOBS_READ_API_KEY`` is set.

    Accepts the configured read key or the admin key. Deployments that have
    not configured a read key keep the documented demo behaviour (open reads).
    """
    settings = get_settings()
    if not settings.read_api_key:
        return
    if (
        x_admin_key
        and settings.admin_api_key
        and hmac.compare_digest(x_admin_key, settings.admin_api_key)
    ):
        return
    if x_api_key and hmac.compare_digest(x_api_key, settings.read_api_key):
        return
    raise HTTPException(status_code=401, detail="read access requires an API key")


def _user_from_key(session: Session, key: str | None) -> User | None:
    if not key:
        return None
    return session.execute(
        select(User).where(User.api_key_hash == hash_api_key(key))
    ).scalar_one_or_none()


def require_role(*roles: str):
    """Role gate for read endpoints (RBAC identities, F06/F16).

    Enforcement is active when ``AIOBS_READ_API_KEY`` is configured (the same
    switch as read auth): the service read key and the admin key bypass role
    checks; otherwise a user API key must match its role for the endpoint.
    With no read key configured (demo mode) reads stay open.

    Usage: ``APIRouter(dependencies=[Depends(require_role("sdm", "finance"))])``.
    """

    def dependency(
        session: Session = Depends(get_db),
        x_api_key: str | None = Header(default=None),
        x_admin_key: str | None = Header(default=None),
    ) -> None:
        settings = get_settings()
        if not settings.read_api_key:
            return
        if (
            x_admin_key
            and settings.admin_api_key
            and hmac.compare_digest(x_admin_key, settings.admin_api_key)
        ):
            return
        if x_api_key and hmac.compare_digest(x_api_key, settings.read_api_key):
            return
        user = _user_from_key(session, x_api_key)
        if user is None or not user.enabled:
            raise HTTPException(status_code=401, detail="invalid API key")
        if roles and user.role != "admin" and user.role not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"role {user.role!r} cannot access this resource",
            )

    return dependency