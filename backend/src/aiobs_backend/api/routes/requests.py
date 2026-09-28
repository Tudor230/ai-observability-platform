"""Self-service requests: org-unit creation and membership changes (ADR-0006)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...models import (
    AccessRequest,
    Department,
    Membership,
    Project,
    Team,
    User,
)
from ..deps import AccessScope, get_db, require_access
from ..memberships import (
    add_membership,
    approved_memberships,
    covers_scope,
    effective_roles,
    has_membership,
    is_global,
    normalize_role_scope,
    scope_exists,
)

# Only these roles may ask for a brand-new department (they can become its
# initial manager); engineers and clients cannot request one.
DEPARTMENT_REQUESTERS = {"admin", "exec", "manager"}

router = APIRouter(prefix="/requests", tags=["requests"])

REQUEST_TYPES = ("create_department", "create_team", "create_project", "membership")


class CreateDepartmentPayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class CreateTeamPayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    department_id: str = Field(min_length=1, max_length=32)


class CreateProjectPayload(BaseModel):
    project_id: str = Field(min_length=2, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    team_id: str = Field(min_length=1, max_length=32)


class MembershipPayload(BaseModel):
    role: Literal["admin", "exec", "manager", "engineer", "client"]
    scope_type: Literal["global", "department", "team", "project"]
    scope_id: str | None = Field(default=None, max_length=32)


PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    "create_department": CreateDepartmentPayload,
    "create_team": CreateTeamPayload,
    "create_project": CreateProjectPayload,
    "membership": MembershipPayload,
}


class RequestIn(BaseModel):
    type: Literal["create_department", "create_team", "create_project", "membership"]
    payload: dict


class RejectIn(BaseModel):
    reason: str | None = None


def _validate_payload(session: Session, req_type: str, payload: dict) -> dict:
    model = PAYLOAD_MODELS.get(req_type)
    if model is None:
        raise HTTPException(status_code=422, detail=f"unknown request type {req_type!r}")
    try:
        data = model.model_validate(payload).model_dump()
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    if req_type == "create_team":
        if session.get(Department, data["department_id"]) is None:
            raise HTTPException(status_code=404, detail="unknown department")
    elif req_type == "create_project":
        if session.get(Team, data["team_id"]) is None:
            raise HTTPException(status_code=404, detail="unknown team")
    elif req_type == "membership":
        data["scope_id"] = normalize_role_scope(
            data["role"], data["scope_type"], data["scope_id"]
        )
        if not scope_exists(session, data["scope_type"], data["scope_id"]):
            raise HTTPException(status_code=404, detail="unknown scope")
    return data


def _can_approve(session: Session, memberships: list[Membership], req: AccessRequest) -> bool:
    if is_global(memberships, "admin", "exec"):
        return True
    payload = req.payload or {}
    if req.type == "create_department":
        return False  # admin/exec only
    if req.type == "create_team":
        return covers_scope(session, memberships, "department", payload.get("department_id"))
    if req.type == "create_project":
        return covers_scope(session, memberships, "team", payload.get("team_id"))
    if req.type == "membership":
        if payload.get("role") in ("admin", "exec", "manager") or payload.get(
            "scope_type"
        ) == "global":
            return False  # manager grants are admin/exec only
        return covers_scope(
            session, memberships, payload.get("scope_type", ""), payload.get("scope_id")
        )
    return False


def _item(
    session: Session,
    req: AccessRequest,
    emails: dict[str, str],
    *,
    viewer_id: str | None,
    can_approve: bool,
) -> dict:
    return {
        "id": req.id,
        "type": req.type,
        "status": req.status,
        "payload": req.payload,
        "requester_id": req.requester_id,
        "requester_email": emails.get(req.requester_id),
        "approver_id": req.approver_id,
        "approver_email": emails.get(req.approver_id) if req.approver_id else None,
        "reason": req.reason,
        "created_at": req.created_at.isoformat() if req.created_at else None,
        "decided_at": req.decided_at.isoformat() if req.decided_at else None,
        "mine": viewer_id is not None and req.requester_id == viewer_id,
        "can_approve": can_approve,
    }


@router.get("")
def list_requests(
    view: str = Query(default="all", pattern="^(all|mine|to_approve)$"),
    access: AccessScope = Depends(require_access()),
    session: Session = Depends(get_db),
) -> dict:
    """Requests the caller made or can decide on."""
    memberships = (
        approved_memberships(session, access.user.id) if access.user else []
    )
    rows = session.execute(
        select(AccessRequest).order_by(AccessRequest.created_at.desc()).limit(500)
    ).scalars().all()
    user_ids = {r.requester_id for r in rows} | {
        r.approver_id for r in rows if r.approver_id
    }
    emails: dict[str, str] = (
        {
            user_id: email
            for user_id, email in session.execute(
                select(User.id, User.email).where(User.id.in_(user_ids))
            ).all()
        }
        if user_ids
        else {}
    )

    items = []
    pending_approvals = 0
    for req in rows:
        mine = access.user is not None and req.requester_id == access.user.id
        can = (
            True
            if access.unrestricted
            else _can_approve(session, memberships, req) if access.user else False
        )
        is_pending_approval = req.status == "pending" and can
        if is_pending_approval:
            pending_approvals += 1
        if view == "mine" and not mine:
            continue
        if view == "to_approve" and not is_pending_approval:
            continue
        if view == "all" and not (mine or is_pending_approval):
            continue
        items.append(
            _item(
                session,
                req,
                emails,
                viewer_id=access.user.id if access.user else None,
                can_approve=can,
            )
        )
    return {
        "items": items,
        "total": len(items),
        "pending_approvals": pending_approvals,
    }


@router.post("")
def create_request(
    body: RequestIn,
    access: AccessScope = Depends(require_access()),
    session: Session = Depends(get_db),
) -> dict:
    if access.user is None:
        raise HTTPException(status_code=403, detail="a user session is required")
    memberships = approved_memberships(session, access.user.id)
    if (
        body.type == "create_department"
        and not (effective_roles(memberships) & DEPARTMENT_REQUESTERS)
    ):
        raise HTTPException(
            status_code=403,
            detail="only managers, executives, and admins can request new departments",
        )
    data = _validate_payload(session, body.type, body.payload)
    if body.type == "membership" and has_membership(
        session,
        user_id=access.user.id,
        role=data["role"],
        scope_type=data["scope_type"],
        scope_id=data.get("scope_id"),
    ):
        raise HTTPException(
            status_code=409, detail="you already hold this membership"
        )
    pending = session.execute(
        select(AccessRequest).where(
            AccessRequest.requester_id == access.user.id,
            AccessRequest.type == body.type,
            AccessRequest.status == "pending",
        )
    ).scalars().all()
    normalized = json.loads(json.dumps(data, sort_keys=True))
    if any(json.loads(json.dumps(r.payload or {}, sort_keys=True)) == normalized for r in pending):
        raise HTTPException(status_code=409, detail="an identical request is already pending")
    req = AccessRequest(type=body.type, requester_id=access.user.id, payload=data)
    if _can_approve(session, memberships, req):
        # Self-approval: a requester who already covers the scope (admin
        # creating a department, manager creating a team/project, ...) skips
        # the queue and materializes immediately (ADR-0007).
        req.approver_id = access.user.id
        req.decided_at = datetime.now(timezone.utc)
        _materialize(session, req)
        req.status = "approved"
        session.add(req)
        session.flush()
        session.commit()
        return _item(
            session,
            req,
            {access.user.id: access.user.email},
            viewer_id=access.user.id,
            can_approve=True,
        )
    session.add(req)
    session.flush()
    session.commit()
    return _item(session, req, {}, viewer_id=access.user.id, can_approve=False)


def _load_pending(session: Session, request_id: str) -> AccessRequest:
    req = session.get(AccessRequest, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="request not found")
    if req.status != "pending":
        raise HTTPException(status_code=409, detail="request has already been decided")
    return req


def _require_approver(
    session: Session, access: AccessScope, req: AccessRequest
) -> User | None:
    if access.unrestricted:
        return access.user
    if access.user is None:
        raise HTTPException(status_code=403, detail="not allowed to decide this request")
    memberships = approved_memberships(session, access.user.id)
    if not _can_approve(session, memberships, req):
        raise HTTPException(status_code=403, detail="not allowed to decide this request")
    return access.user


def _materialize(session: Session, req: AccessRequest) -> None:
    payload = req.payload or {}
    try:
        if req.type == "create_department":
            name = payload["name"]
            exists = session.execute(
                select(Department.id).where(Department.name == name)
            ).first()
            if exists:
                raise HTTPException(status_code=409, detail="department name already exists")
            department = Department(name=name)
            session.add(department)
            session.flush()
            # The requester becomes the department's initial manager (ticket 05).
            add_membership(
                session,
                user_id=req.requester_id,
                role="manager",
                scope_type="department",
                scope_id=department.id,
                requested_by=req.requester_id,
                approved_by=req.approver_id,
            )
        elif req.type == "create_team":
            existing_department = session.get(Department, payload["department_id"])
            if existing_department is None:
                raise HTTPException(status_code=409, detail="department no longer exists")
            session.add(
                Team(name=payload["name"], department_id=existing_department.id)
            )
        elif req.type == "create_project":
            team = session.get(Team, payload["team_id"])
            if team is None:
                raise HTTPException(status_code=409, detail="team no longer exists")
            exists = session.execute(
                select(Project.id).where(Project.project_id == payload["project_id"])
            ).first()
            if exists:
                raise HTTPException(status_code=409, detail="project_id already exists")
            # Keys are added post-approval by a member (plans/roles.md §5.3).
            session.add(
                Project(
                    team_id=team.id,
                    project_id=payload["project_id"],
                    name=payload["name"],
                )
            )
        elif req.type == "membership":
            add_membership(
                session,
                user_id=req.requester_id,
                role=payload["role"],
                scope_type=payload["scope_type"],
                scope_id=payload.get("scope_id"),
                requested_by=req.requester_id,
                approved_by=req.approver_id,
            )
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="request conflicts with existing data"
        ) from exc


@router.post("/{request_id}/approve")
def approve_request(
    request_id: str,
    access: AccessScope = Depends(require_access()),
    session: Session = Depends(get_db),
) -> dict:
    req = _load_pending(session, request_id)
    approver = _require_approver(session, access, req)
    req.approver_id = approver.id if approver else None
    req.decided_at = datetime.now(timezone.utc)
    _materialize(session, req)
    req.status = "approved"
    session.flush()
    session.commit()
    return {"id": req.id, "status": req.status}


@router.post("/{request_id}/reject")
def reject_request(
    request_id: str,
    body: RejectIn,
    access: AccessScope = Depends(require_access()),
    session: Session = Depends(get_db),
) -> dict:
    reason = (body.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=422, detail="a rejection reason is required")
    req = _load_pending(session, request_id)
    approver = _require_approver(session, access, req)
    req.status = "rejected"
    req.reason = reason
    req.approver_id = approver.id if approver else None
    req.decided_at = datetime.now(timezone.utc)
    session.flush()
    session.commit()
    return {"id": req.id, "status": req.status, "reason": req.reason}


@router.post("/{request_id}/cancel")
def cancel_request(
    request_id: str,
    access: AccessScope = Depends(require_access()),
    session: Session = Depends(get_db),
) -> dict:
    req = _load_pending(session, request_id)
    if access.user is None or req.requester_id != access.user.id:
        raise HTTPException(status_code=403, detail="only the requester can cancel")
    req.status = "cancelled"
    req.decided_at = datetime.now(timezone.utc)
    session.flush()
    session.commit()
    return {"id": req.id, "status": req.status}
