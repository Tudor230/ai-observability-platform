"""Membership domain helpers: role/scope derivation, coverage, and naming.

Memberships are the single source of truth for authorization (ADR-0006); the
effective scope is the union of approved grants. Scope pointers are polymorphic
(`scope_type` + `scope_id`, no FK), so existence/name lookups live here too.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import ROLE_SCOPES, Department, Membership, Project, Team

APPROVED = "approved"
SCOPE_MODELS: dict[str, type[Department] | type[Team] | type[Project]] = {
    "department": Department,
    "team": Team,
    "project": Project,
}


def approved_memberships(session: Session, user_id: str) -> list[Membership]:
    return list(
        session.execute(
            select(Membership)
            .where(Membership.user_id == user_id, Membership.status == APPROVED)
            .order_by(Membership.created_at)
        )
        .scalars()
        .all()
    )


def effective_roles(memberships: list[Membership]) -> set[str]:
    return {m.role for m in memberships if m.status == APPROVED}


def has_membership(
    session: Session,
    *,
    user_id: str,
    role: str,
    scope_type: str,
    scope_id: str | None,
) -> bool:
    """True when the user already holds this exact approved grant."""
    stmt = select(Membership.id).where(
        Membership.user_id == user_id,
        Membership.role == role,
        Membership.scope_type == scope_type,
        Membership.status == APPROVED,
    )
    stmt = stmt.where(
        Membership.scope_id.is_(None) if scope_id is None else Membership.scope_id == scope_id
    )
    return session.execute(stmt).first() is not None


def is_global(memberships: list[Membership], *roles: str) -> bool:
    """True when the user holds an approved global grant with one of ``roles``."""
    wanted = set(roles)
    for m in memberships:
        if m.status != APPROVED or m.scope_type != "global":
            continue
        if not wanted or m.role in wanted:
            return True
    return False


def allowed_project_ids(
    session: Session, memberships: list[Membership]
) -> frozenset[str] | None:
    """External project_id values the memberships grant access to.

    ``None`` means unrestricted: any global grant (admin/exec) sees everything.
    """
    department_ids: set[str] = set()
    team_ids: set[str] = set()
    project_ids: set[str] = set()
    for m in memberships:
        if m.status != APPROVED:
            continue
        if m.scope_type == "global":
            return None
        if not m.scope_id:
            continue
        if m.scope_type == "department":
            department_ids.add(m.scope_id)
        elif m.scope_type == "team":
            team_ids.add(m.scope_id)
        elif m.scope_type == "project":
            project_ids.add(m.scope_id)
    conditions = []
    if department_ids:
        conditions.append(Team.department_id.in_(department_ids))
    if team_ids:
        conditions.append(Project.team_id.in_(team_ids))
    if project_ids:
        conditions.append(Project.id.in_(project_ids))
    if not conditions:
        return frozenset()
    rows = session.execute(
        select(Project.project_id)
        .join(Team, Team.id == Project.team_id)
        .where(or_(*conditions))
    ).scalars().all()
    return frozenset(rows)


def _project_ancestors(session: Session, project_id: str) -> tuple[str | None, str | None]:
    row = session.execute(
        select(Project.team_id, Team.department_id)
        .join(Team, Team.id == Project.team_id)
        .where(Project.id == project_id)
    ).first()
    return (row[0], row[1]) if row else (None, None)


def _team_department(session: Session, team_id: str) -> str | None:
    return session.execute(
        select(Team.department_id).where(Team.id == team_id)
    ).scalar_one_or_none()


def covers_scope(
    session: Session, memberships: list[Membership], scope_type: str, scope_id: str | None
) -> bool:
    """True when the caller manages (or globally administers) the target scope.

    Department managers cover their teams and those teams' projects; team
    managers cover their projects.
    """
    if scope_type == "global" or not scope_id:
        return False
    team_id: str | None = None
    department_id: str | None = None
    if scope_type == "project":
        team_id, department_id = _project_ancestors(session, scope_id)
    elif scope_type == "team":
        team_id = scope_id
        department_id = _team_department(session, scope_id)
    elif scope_type == "department":
        department_id = scope_id
    for m in memberships:
        if m.status != APPROVED or m.role not in ("admin", "exec", "manager"):
            continue
        if m.scope_type == "global":
            return True
        if not m.scope_id:
            continue
        if m.scope_type == "department" and department_id and m.scope_id == department_id:
            return True
        if m.scope_type == "team" and team_id and m.scope_id == team_id:
            return True
        if m.scope_type == "project" and scope_type == "project" and m.scope_id == scope_id:
            return True
    return False


def normalize_role_scope(role: str, scope_type: str, scope_id: str | None) -> str | None:
    """Validate the role/scope matrix; returns the normalized scope_id.

    422s on an unknown role or a scope the role cannot hold; global scope is
    stored as NULL.
    """
    if scope_type == "global":
        return None
    if role not in ROLE_SCOPES:
        raise HTTPException(status_code=422, detail=f"unknown role {role!r}")
    if not scope_id:
        raise HTTPException(status_code=422, detail="scope_id is required")
    if scope_type not in ROLE_SCOPES[role]:
        raise HTTPException(
            status_code=422,
            detail=f"role {role} cannot be granted at {scope_type} scope",
        )
    return scope_id


def add_membership(
    session: Session,
    *,
    user_id: str,
    role: str,
    scope_type: str,
    scope_id: str | None,
    requested_by: str | None = None,
    approved_by: str | None = None,
) -> Membership:
    """Create an approved membership, guarding the active-grant uniqueness."""
    stmt = select(Membership.id).where(
        Membership.user_id == user_id,
        Membership.role == role,
        Membership.scope_type == scope_type,
        Membership.status == APPROVED,
    )
    stmt = stmt.where(
        Membership.scope_id.is_(None) if scope_id is None else Membership.scope_id == scope_id
    )
    if session.execute(stmt).first():
        raise HTTPException(
            status_code=409, detail="user already holds this approved membership"
        )
    membership = Membership(
        user_id=user_id,
        role=role,
        scope_type=scope_type,
        scope_id=scope_id,
        status=APPROVED,
        requested_by=requested_by,
        approved_by=approved_by,
        decided_at=datetime.now(timezone.utc),
    )
    session.add(membership)
    session.flush()
    return membership


def scope_exists(session: Session, scope_type: str, scope_id: str | None) -> bool:
    if scope_type == "global":
        return scope_id is None
    model = SCOPE_MODELS.get(scope_type)
    if model is None or not scope_id:
        return False
    return session.execute(select(model.id).where(model.id == scope_id)).first() is not None


def scope_name(session: Session, scope_type: str, scope_id: str | None) -> str | None:
    if scope_type == "global" or not scope_id:
        return "Global"
    model = SCOPE_MODELS.get(scope_type)
    if model is None:
        return None
    return session.execute(select(model.name).where(model.id == scope_id)).scalar_one_or_none()


def membership_dict(session: Session, m: Membership) -> dict:
    return {
        "id": m.id,
        "role": m.role,
        "scope_type": m.scope_type,
        "scope_id": m.scope_id,
        "scope_name": scope_name(session, m.scope_type, m.scope_id),
        "status": m.status,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def user_dict(user) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "enabled": user.enabled,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }
