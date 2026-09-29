"""Users (admin): provision accounts, reset passwords, grant memberships."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Membership, User
from ...security import (
    generate_api_key,
    generate_password,
    hash_api_key,
    hash_password,
)
from ..deps import get_admin_key, get_db
from ..memberships import (
    add_membership,
    membership_dict,
    normalize_role_scope,
    scope_exists,
)

router = APIRouter(tags=["users"], dependencies=[Depends(get_admin_key)])


class UserIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    # Optional: a generated password is returned once when omitted.
    password: str | None = Field(default=None, min_length=8, max_length=200)


class MembershipIn(BaseModel):
    role: Literal["admin", "exec", "manager", "engineer", "client"]
    scope_type: Literal["global", "department", "team", "project"]
    scope_id: str | None = Field(default=None, max_length=32)


class UserOut(BaseModel):
    id: str
    email: str
    api_key: str
    password: str | None = None


class PasswordOut(BaseModel):
    id: str
    email: str
    password: str


def _memberships_by_user(session: Session) -> dict[str, list[Membership]]:
    grouped: dict[str, list[Membership]] = {}
    rows = session.execute(
        select(Membership)
        .where(Membership.status == "approved")
        .order_by(Membership.created_at)
    ).scalars().all()
    for membership in rows:
        grouped.setdefault(membership.user_id, []).append(membership)
    return grouped


@router.get("/users")
def list_users(session: Session = Depends(get_db)) -> dict:
    rows = session.execute(select(User).order_by(User.created_at)).scalars().all()
    by_user = _memberships_by_user(session)
    items = [
        {
            "id": u.id,
            "email": u.email,
            "roles": sorted({m.role for m in by_user.get(u.id, [])}),
            "memberships": [
                membership_dict(session, m) for m in by_user.get(u.id, [])
            ],
            "enabled": u.enabled,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in rows
    ]
    return {"items": items, "total": len(items)}


@router.post("/users", response_model=UserOut)
def create_user(body: UserIn, session: Session = Depends(get_db)) -> UserOut:
    existing = session.execute(
        select(User.id).where(User.email == body.email)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="email already exists")
    key = generate_api_key()
    password = body.password or generate_password()
    user = User(
        email=body.email,
        password_hash=hash_password(password),
        api_key_hash=hash_api_key(key),
    )
    session.add(user)
    session.flush()
    session.commit()  # before the response: see the ingest route note
    return UserOut(id=user.id, email=user.email, api_key=key, password=password)


def _user_row(session: Session, user_id: str) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return user


@router.post("/users/{user_id}/reset-password", response_model=PasswordOut)
def reset_password(user_id: str, session: Session = Depends(get_db)) -> PasswordOut:
    """Set a fresh password (returned once) and revoke existing sessions."""
    user = _user_row(session, user_id)
    password = generate_password()
    user.password_hash = hash_password(password)
    user.token_version += 1
    session.flush()
    session.commit()
    return PasswordOut(id=user.id, email=user.email, password=password)


@router.post("/users/{user_id}/memberships")
def grant_membership(
    user_id: str, body: MembershipIn, session: Session = Depends(get_db)
) -> dict:
    """Admin override: grant an approved membership without the request flow."""
    _user_row(session, user_id)
    scope_id = normalize_role_scope(body.role, body.scope_type, body.scope_id)
    if not scope_exists(session, body.scope_type, scope_id):
        raise HTTPException(status_code=404, detail="unknown scope")
    membership = add_membership(
        session,
        user_id=user_id,
        role=body.role,
        scope_type=body.scope_type,
        scope_id=scope_id,
    )
    session.commit()
    return membership_dict(session, membership)


@router.delete("/users/{user_id}/memberships/{membership_id}")
def revoke_membership(
    user_id: str, membership_id: str, session: Session = Depends(get_db)
) -> dict:
    """Soft-revoke a membership: it stays for audit but no longer grants access."""
    membership = session.execute(
        select(Membership).where(
            Membership.id == membership_id, Membership.user_id == user_id
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=404, detail="membership not found")
    if membership.status == "approved":
        membership.status = "revoked"
        membership.decided_at = datetime.now(timezone.utc)
        session.flush()
        session.commit()
    return {"id": membership.id, "status": membership.status}


def _set_enabled(session: Session, user_id: str, enabled: bool) -> dict:
    user = _user_row(session, user_id)
    user.enabled = enabled
    # Bump the token version so disabling/enabling revokes outstanding sessions.
    user.token_version += 1
    session.flush()
    session.commit()
    return {"id": user.id, "email": user.email, "enabled": user.enabled}


@router.post("/users/{user_id}/disable")
def disable_user(user_id: str, session: Session = Depends(get_db)) -> dict:
    return _set_enabled(session, user_id, enabled=False)


@router.post("/users/{user_id}/enable")
def enable_user(user_id: str, session: Session = Depends(get_db)) -> dict:
    return _set_enabled(session, user_id, enabled=True)
