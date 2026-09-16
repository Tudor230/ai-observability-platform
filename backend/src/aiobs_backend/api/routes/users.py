"""Users (admin): create platform identities with roles and mint API keys (RBAC)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import User
from ...security import generate_api_key, hash_api_key
from ..deps import get_admin_key, get_db

router = APIRouter(tags=["users"], dependencies=[Depends(get_admin_key)])


class UserIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    role: str = Field(default="engineer", pattern="^(admin|engineer|sdm|finance)$")


class UserOut(BaseModel):
    id: str
    email: str
    role: str
    api_key: str


@router.get("/users")
def list_users(session: Session = Depends(get_db)) -> dict:
    rows = session.execute(select(User).order_by(User.created_at)).scalars().all()
    items = [
        {
            "id": u.id,
            "email": u.email,
            "role": u.role,
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
    user = User(
        email=body.email,
        role=body.role,
        api_key_hash=hash_api_key(key),
    )
    session.add(user)
    session.flush()
    session.commit()  # before the response: see the ingest route note
    return UserOut(id=user.id, email=user.email, role=user.role, api_key=key)


def _set_enabled(session: Session, user_id: str, enabled: bool) -> dict:
    user = session.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    user.enabled = enabled
    session.flush()
    session.commit()
    return {"id": user.id, "email": user.email, "enabled": user.enabled}


@router.post("/users/{user_id}/disable")
def disable_user(user_id: str, session: Session = Depends(get_db)) -> dict:
    return _set_enabled(session, user_id, enabled=False)


@router.post("/users/{user_id}/enable")
def enable_user(user_id: str, session: Session = Depends(get_db)) -> dict:
    return _set_enabled(session, user_id, enabled=True)
