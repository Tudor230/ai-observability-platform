"""Project rates: versioned revenue and manual-cost inputs (ADR-0013).

A rate is a *version*, not a mutable singleton: each row carries an explicit
``effective_from`` and the active rate for a day is the greatest
``effective_from <= day``. Adding a version never overwrites an older one — a
duplicate date for the same project is a 409 — and versions stay editable.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...models import Project, ProjectRate
from ..deps import AccessScope, get_db, require_access
from ..serialize import money

router = APIRouter(tags=["project-rates"])


class RateIn(BaseModel):
    project_id: str = Field(min_length=1, max_length=32)
    effective_from: date
    revenue_amount: float = Field(ge=0)
    revenue_period: Literal["month", "year"] = "month"
    manual_cost_amount: float = Field(default=0.0, ge=0)
    manual_cost_period: Literal["month", "year"] = "month"


class RateUpdate(BaseModel):
    effective_from: date | None = None
    revenue_amount: float | None = Field(default=None, ge=0)
    revenue_period: Literal["month", "year"] | None = None
    manual_cost_amount: float | None = Field(default=None, ge=0)
    manual_cost_period: Literal["month", "year"] | None = None


def _rate_dict(rate: ProjectRate, project_ext: str, project_name: str | None) -> dict:
    return {
        "id": rate.id,
        "project_id": project_ext,
        "project_name": project_name,
        "effective_from": rate.effective_from.isoformat(),
        "revenue_amount": money(rate.revenue_amount),
        "revenue_period": rate.revenue_period,
        "manual_cost_amount": money(rate.manual_cost_amount),
        "manual_cost_period": rate.manual_cost_period,
        "currency": rate.currency,
        "updated_at": rate.updated_at.isoformat() if rate.updated_at else None,
    }


def _project(session: Session, project_ext: str) -> Project:
    project = session.execute(
        select(Project).where(Project.project_id == project_ext)
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail=f"unknown project {project_ext}")
    return project


@router.get("/project-rates")
def list_rates(
    session: Session = Depends(get_db),
    access: AccessScope = Depends(require_access("exec")),
) -> dict:
    """Every project with its internal flag and its rate versions, newest first.

    Projects without versions are included: the editor has to be able to add the
    first version, and to flag internal projects that need no revenue at all.
    """
    projects = session.execute(
        select(Project).order_by(Project.name)
    ).scalars().all()
    versions: dict[str, list[ProjectRate]] = {}
    rows = session.execute(
        select(ProjectRate).order_by(ProjectRate.effective_from.desc())
    ).scalars().all()
    for rate in rows:
        versions.setdefault(rate.project_id, []).append(rate)

    items = [
        {
            "project_id": project.project_id,
            "project_name": project.name,
            "internal": bool(project.internal),
            "versions": [
                _rate_dict(rate, project.project_id, project.name)
                for rate in versions.get(project.id, [])
            ],
        }
        for project in projects
    ]
    return {"items": items, "total": len(items)}


@router.post("/project-rates")
def create_rate(
    body: RateIn,
    session: Session = Depends(get_db),
    access: AccessScope = Depends(require_access("exec")),
) -> dict:
    project = _project(session, body.project_id)
    rate = ProjectRate(
        project_id=project.id,
        effective_from=body.effective_from,
        revenue_amount=Decimal(str(body.revenue_amount)),
        revenue_period=body.revenue_period,
        manual_cost_amount=Decimal(str(body.manual_cost_amount)),
        manual_cost_period=body.manual_cost_period,
        updated_by=access.user.id if access.user else None,
    )
    session.add(rate)
    try:
        session.flush()
    except IntegrityError as err:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                f"a rate for {body.project_id} already starts on "
                f"{body.effective_from.isoformat()}"
            ),
        ) from err
    session.commit()
    return _rate_dict(rate, project.project_id, project.name)


@router.patch("/project-rates/{rate_id}")
def update_rate(
    rate_id: str,
    body: RateUpdate,
    session: Session = Depends(get_db),
    access: AccessScope = Depends(require_access("exec")),
) -> dict:
    rate = session.get(ProjectRate, rate_id)
    if rate is None:
        raise HTTPException(status_code=404, detail=f"unknown rate {rate_id}")
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        if field in ("revenue_amount", "manual_cost_amount"):
            setattr(rate, field, Decimal(str(value)))
        else:
            setattr(rate, field, value)
    rate.updated_by = access.user.id if access.user else None
    try:
        session.flush()
    except IntegrityError as err:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="another rate version already starts on that date",
        ) from err
    session.commit()
    project = session.get(Project, rate.project_id)
    return _rate_dict(
        rate,
        project.project_id if project else "",
        project.name if project else None,
    )


class InternalIn(BaseModel):
    internal: bool


@router.patch("/project-rates/{project_id}/internal")
def set_internal(
    project_id: str,
    body: InternalIn,
    session: Session = Depends(get_db),
    access: AccessScope = Depends(require_access("exec")),
) -> dict:
    """Flag a project as internal: no revenue is expected from it (ADR-0013)."""
    project = _project(session, project_id)
    project.internal = body.internal
    session.commit()
    return {
        "project_id": project.project_id,
        "project_name": project.name,
        "internal": bool(project.internal),
    }


@router.delete("/project-rates/{rate_id}")
def delete_rate(
    rate_id: str,
    session: Session = Depends(get_db),
    access: AccessScope = Depends(require_access("exec")),
) -> dict:
    rate = session.get(ProjectRate, rate_id)
    if rate is None:
        raise HTTPException(status_code=404, detail=f"unknown rate {rate_id}")
    session.delete(rate)
    session.commit()
    return {"deleted": rate_id}
