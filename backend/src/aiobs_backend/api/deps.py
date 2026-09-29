"""Shared FastAPI dependencies: DB session, auth, and scope-derived access."""
from __future__ import annotations

import hmac
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import session_scope
from ..models import Project, ProjectKey, User
from ..security import (
    SESSION_COOKIE,
    decode_session_token,
    hash_api_key,
    verify_api_key,
)
from .memberships import (
    allowed_project_ids,
    approved_memberships,
    effective_roles,
    is_global,
)


def get_db() -> Iterator[Session]:
    with session_scope() as session:
        yield session


def _session_user(request: Request, session: Session) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    payload = decode_session_token(token, get_settings().jwt_secret)
    if not payload:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    user = session.get(User, user_id)
    if user is None or not user.enabled:
        return None
    if payload.get("ver") != user.token_version:
        return None
    return user


def get_current_user(
    request: Request, session: Session = Depends(get_db)
) -> User:
    """Strict session auth: the JWT cookie must resolve to an enabled user."""
    user = _session_user(request, session)
    if user is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    return user


def _user_from_key(session: Session, key: str | None) -> User | None:
    if not key:
        return None
    return session.execute(
        select(User).where(User.api_key_hash == hash_api_key(key))
    ).scalar_one_or_none()


def get_admin_key(
    request: Request,
    x_admin_key: str | None = Header(default=None),
    session: Session = Depends(get_db),
) -> str:
    """Admin access: the `x-admin-key` service key or a global-admin session."""
    settings = get_settings()
    if (
        x_admin_key
        and settings.admin_api_key
        and hmac.compare_digest(x_admin_key, settings.admin_api_key)
    ):
        return "admin-key"
    user = _session_user(request, session)
    if user is not None and is_global(approved_memberships(session, user.id), "admin"):
        return f"session:{user.id}"
    raise HTTPException(status_code=401, detail="admin access required")


def _validated_header_project(session: Session, project: str | None) -> str | None:
    if not project:
        return None
    exists = session.execute(
        select(Project.id).where(Project.project_id == project)
    ).first()
    if exists is None:
        raise HTTPException(status_code=404, detail=f"unknown project {project}")
    return project


@dataclass(frozen=True)
class AccessScope:
    """Resolved caller: roles, allowed projects, and cost visibility."""

    roles: frozenset[str]
    project_ids: frozenset[str] | None  # None = every project
    unrestricted: bool
    header_project: str | None = None
    user: User | None = None

    @property
    def cost_visible(self) -> bool:
        # Clients never receive cost fields; any other role's membership reveals
        # them (ADR-0006, plans/roles.md §6.3).
        return self.unrestricted or bool(self.roles - {"client"})

    def resolve_project_filter(self, requested: str | None) -> frozenset[str] | None:
        """Fold a query param/header scope into the allowed set (404 if denied)."""
        requested = requested or self.header_project
        if requested:
            if self.project_ids is not None and requested not in self.project_ids:
                raise HTTPException(
                    status_code=404, detail=f"unknown project {requested}"
                )
            return frozenset({requested})
        return self.project_ids

    def ensure_visible(self, project_ext: str | None, detail: str = "not found") -> None:
        if self.header_project and project_ext != self.header_project:
            raise HTTPException(status_code=404, detail=detail)
        if self.project_ids is not None and project_ext not in self.project_ids:
            raise HTTPException(status_code=404, detail=detail)


def require_access(*roles: str):
    """Scope-derived access gate for read endpoints (ADR-0006).

    Resolves the caller from the session cookie, a user API key, the service
    read key, or the admin key. User callers must hold one of ``roles`` unless
    they hold a global grant; their allowed projects are the union of approved
    memberships. Admin/service callers are unrestricted.
    """

    def dependency(
        request: Request,
        session: Session = Depends(get_db),
        x_api_key: str | None = Header(default=None),
        x_admin_key: str | None = Header(default=None),
        x_project_name: str | None = Header(default=None),
    ) -> AccessScope:
        settings = get_settings()
        if (
            x_admin_key
            and settings.admin_api_key
            and hmac.compare_digest(x_admin_key, settings.admin_api_key)
        ):
            return AccessScope(
                frozenset({"admin"}),
                None,
                True,
                _validated_header_project(session, x_project_name),
            )
        if (
            x_api_key
            and settings.read_api_key
            and hmac.compare_digest(x_api_key, settings.read_api_key)
        ):
            return AccessScope(
                frozenset({"admin"}),
                None,
                True,
                _validated_header_project(session, x_project_name),
            )
        user = _session_user(request, session) or _user_from_key(session, x_api_key)
        if user is None or not user.enabled:
            raise HTTPException(status_code=401, detail="authentication required")
        memberships = approved_memberships(session, user.id)
        roles_set = effective_roles(memberships)
        if is_global(memberships, "admin"):
            return AccessScope(
                frozenset(roles_set | {"admin"}),
                None,
                True,
                _validated_header_project(session, x_project_name),
                user,
            )
        if roles and not (roles_set & set(roles)):
            raise HTTPException(
                status_code=403,
                detail=f"roles {sorted(roles_set)} cannot access this resource",
            )
        header_project = _validated_header_project(session, x_project_name)
        scope = AccessScope(
            frozenset(roles_set),
            allowed_project_ids(session, memberships),
            False,
            header_project,
            user,
        )
        if header_project:
            scope.resolve_project_filter(header_project)
        return scope

    return dependency


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
    active_keys = session.execute(
        select(ProjectKey).where(
            ProjectKey.project_id == project.id,
            ProjectKey.revoked_at.is_(None),
        )
    ).scalars().all()
    if not active_keys:
        raise HTTPException(
            status_code=401,
            detail="project has no API keys yet — add one from the project page",
        )
    key = ""
    if authorization and authorization.lower().startswith("bearer "):
        key = authorization[7:]
    for candidate in active_keys:
        if verify_api_key(key, candidate.key_hash):
            candidate.last_used_at = datetime.now(timezone.utc)
            session.flush()
            return project
    raise HTTPException(status_code=401, detail="invalid API key")
