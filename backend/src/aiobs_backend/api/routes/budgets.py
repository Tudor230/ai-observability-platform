"""Budgets: admin CRUD + a read-only status view for the dashboard."""
from __future__ import annotations

from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...alerts import budget_spend, budget_window
from ...models import Budget, Client, Project
from ..deps import get_admin_key, get_db, require_read_access

router = APIRouter(tags=["budgets"])


class BudgetIn(BaseModel):
    name: str | None = None
    amount: float = Field(gt=0)
    period: date  # period anchor (day); the current window is derived from it
    period_type: str = Field(default="month", pattern="^(day|week|month)$")
    project: str | None = None  # external project_id
    client: str | None = None  # external client key
    workflow_name: str | None = None


def _resolve_ids(session: Session, project: str | None, client: str | None):
    project_id = None
    if project:
        row = session.execute(
            select(Project.id).where(Project.project_id == project)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=400, detail=f"unknown project {project}")
        project_id = row
    client_id = None
    if client:
        row = session.execute(
            select(Client.id).where(Client.external_key == client)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=400, detail=f"unknown client {client}")
        client_id = row
    return project_id, client_id


@router.get("/budgets", dependencies=[Depends(get_admin_key)])
def list_budgets(session: Session = Depends(get_db)) -> dict:
    rows = session.execute(select(Budget).order_by(Budget.period.desc())).scalars().all()
    items = []
    for b in rows:
        items.append(
            {
                "id": b.id,
                "name": b.name,
                "amount": float(b.amount),
                "period": b.period.isoformat(),
                "period_type": b.period_type or "month",
                "project_id": b.project_id,
                "client_id": b.client_id,
                "workflow_name": b.workflow_name,
            }
        )
    return {"items": items, "total": len(items)}


@router.post("/budgets", dependencies=[Depends(get_admin_key)])
def create_budget(body: BudgetIn, session: Session = Depends(get_db)) -> dict:
    project_id, client_id = _resolve_ids(session, body.project, body.client)
    period = datetime.combine(body.period, time.min, tzinfo=timezone.utc)
    budget = Budget(
        name=body.name,
        amount=body.amount,
        period=period,
        period_type=body.period_type,
        project_id=project_id,
        client_id=client_id,
        workflow_name=body.workflow_name,
    )
    session.add(budget)
    session.flush()
    session.commit()
    return {
        "id": budget.id,
        "amount": float(budget.amount),
        "period": budget.period.isoformat(),
        "period_type": budget.period_type,
    }


@router.delete("/budgets/{budget_id}", dependencies=[Depends(get_admin_key)])
def delete_budget(budget_id: str, session: Session = Depends(get_db)) -> dict:
    budget = session.execute(
        select(Budget).where(Budget.id == budget_id)
    ).scalar_one_or_none()
    if budget is None:
        raise HTTPException(status_code=404, detail="budget not found")
    session.delete(budget)
    session.commit()
    return {"deleted": budget_id}


@router.get("/budgets/status", dependencies=[Depends(require_read_access)])
def budget_status(session: Session = Depends(get_db)) -> dict:
    """Read-only budget utilization for dashboards (no admin key needed).

    ``utilization`` is the true ratio (can exceed 1.0); clients must clamp only
    the bar width, never the number (F23).
    """
    rows = session.execute(select(Budget).order_by(Budget.period.desc())).scalars().all()
    items = []
    for b in rows:
        spend = budget_spend(session, b)
        amount = float(b.amount or 0)
        window_start, window_end = budget_window(b)
        items.append(
            {
                "id": b.id,
                "name": b.name,
                "amount": amount,
                "spend": round(spend, 6),
                "utilization": round(spend / amount, 4) if amount else 0.0,
                "period": b.period.isoformat(),
                "period_type": b.period_type or "month",
                "period_start": window_start.isoformat(),
                "period_end": window_end.isoformat(),
                "workflow_name": b.workflow_name,
            }
        )
    return {"items": items, "total": len(items)}