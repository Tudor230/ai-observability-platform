"""Alert channels: admin/exec-managed delivery targets (audit item 7).

Managers never create channels; they only select enabled ones when editing
their rules (settled decision, spec §8).
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import AlertChannel
from ..deps import AccessScope, get_db, require_access

router = APIRouter(tags=["alert-channels"])

ChannelType = Literal["email", "slack", "webhook"]


class ChannelIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: ChannelType
    target: str = Field(min_length=1, max_length=320)
    enabled: bool = True


class ChannelPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    type: ChannelType | None = None
    target: str | None = Field(default=None, min_length=1, max_length=320)
    enabled: bool | None = None


def _validate_target(channel_type: str, target: str) -> None:
    if channel_type == "email":
        if "@" not in target:
            raise HTTPException(status_code=422, detail="email target must be an address")
    elif not target.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="target must be an http(s) URL")


def _channel_dict(channel: AlertChannel) -> dict:
    return {
        "id": channel.id,
        "name": channel.name,
        "type": channel.type,
        "target": channel.target,
        "enabled": channel.enabled,
        "created_at": channel.created_at.isoformat() if channel.created_at else None,
    }


def _load_channel(session: Session, channel_id: str) -> AlertChannel:
    channel = session.get(AlertChannel, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="alert channel not found")
    return channel


@router.get("/alert-channels")
def list_channels(
    session: Session = Depends(get_db),
    access: AccessScope = Depends(require_access("exec")),
) -> dict:
    rows = (
        session.execute(select(AlertChannel).order_by(AlertChannel.created_at.desc()))
        .scalars()
        .all()
    )
    items = [_channel_dict(c) for c in rows]
    return {"items": items, "total": len(items)}


@router.post("/alert-channels")
def create_channel(
    body: ChannelIn,
    session: Session = Depends(get_db),
    access: AccessScope = Depends(require_access("exec")),
) -> dict:
    _validate_target(body.type, body.target)
    channel = AlertChannel(
        name=body.name,
        type=body.type,
        target=body.target,
        enabled=body.enabled,
        created_by=access.user.id if access.user else None,
    )
    session.add(channel)
    session.flush()
    session.commit()
    return _channel_dict(channel)


@router.patch("/alert-channels/{channel_id}")
def update_channel(
    channel_id: str,
    body: ChannelPatch,
    session: Session = Depends(get_db),
    access: AccessScope = Depends(require_access("exec")),
) -> dict:
    channel = _load_channel(session, channel_id)
    fields = body.model_dump(exclude_unset=True)
    channel_type = body.type if body.type is not None else channel.type
    target = body.target if body.target is not None else channel.target
    _validate_target(channel_type, target)
    if "name" in fields and body.name is not None:
        channel.name = body.name
    if body.type is not None:
        channel.type = body.type
    if body.target is not None:
        channel.target = body.target
    if "enabled" in fields and body.enabled is not None:
        channel.enabled = body.enabled
    session.flush()
    session.commit()
    return _channel_dict(channel)


@router.delete("/alert-channels/{channel_id}")
def delete_channel(
    channel_id: str,
    session: Session = Depends(get_db),
    access: AccessScope = Depends(require_access("exec")),
) -> dict:
    channel = _load_channel(session, channel_id)
    session.delete(channel)
    session.commit()
    return {"deleted": channel_id}
