"""Email/password sessions: login, logout, and the current-user profile."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import get_settings
from ...models import User
from ...security import (
    SESSION_COOKIE,
    create_session_token,
    verify_password,
)
from ..deps import get_current_user, get_db
from ..memberships import approved_memberships, effective_roles, membership_dict, user_dict

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.jwt_ttl_s,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def _profile(session: Session, user: User) -> dict:
    memberships = approved_memberships(session, user.id)
    roles = sorted(effective_roles(memberships))
    return {
        "user": user_dict(user),
        "roles": roles,
        "memberships": [membership_dict(session, m) for m in memberships],
        "can_approve": bool({"manager", "exec", "admin"} & set(roles)),
    }


@router.post("/login")
def login(
    body: LoginIn, response: Response, session: Session = Depends(get_db)
) -> dict:
    user = session.execute(
        select(User).where(User.email == body.email)
    ).scalar_one_or_none()
    if user is None or not user.enabled or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid email or password")
    token = create_session_token(
        user.id,
        user.token_version,
        get_settings().jwt_secret,
        get_settings().jwt_ttl_s,
    )
    _set_session_cookie(response, token)
    return _profile(session, user)


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(
    response: Response,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict:
    """Current profile; re-issues the cookie so active sessions keep sliding."""
    settings = get_settings()
    token = create_session_token(
        user.id, user.token_version, settings.jwt_secret, settings.jwt_ttl_s
    )
    _set_session_cookie(response, token)
    return _profile(session, user)
