"""Budgets (admin): CRUD. Accepts external project/client identifiers."""
from __future__ import annotations

from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Budget, Client, Project
from ..deps import get_admin_key, get_db

router = APIRouter(tags=["budgets"], dependencies=[Depends(get_admin_key)])


class BudgetIn(BaseModel):
    name: str | None = None
    amount: float = Field(gt=0)
    period: date  # period start (day)
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


@router.get("/budgets")
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
                "project_id": b.project_id,
                "client_id": b.client_id,
                "workflow_name": b.workflow_name,
            }
        )
    return {"items": items, "total": len(items)}


@router.post("/budgets")
def create_budget(body: BudgetIn, session: Session = Depends(get_db)) -> dict:
    project_id, client_id = _resolve_ids(session, body.project, body.client)
    period = datetime.combine(body.period, time.min, tzinfo=timezone.utc)
    budget = Budget(
        name=body.name,
        amount=body.amount,
        period=period,
        project_id=project_id,
        client_id=client_id,
        workflow_name=body.workflow_name,
    )
    session.add(budget)
    session.flush()
    return {"id": budget.id, "amount": float(budget.amount), "period": budget.period.isoformat()}


@router.delete("/budgets/{budget_id}")
def delete_budget(budget_id: str, session: Session = Depends(get_db)) -> dict:
    budget = session.execute(
        select(Budget).where(Budget.id == budget_id)
    ).scalar_one_or_none()
    if budget is None:
        raise HTTPException(status_code=404, detail="budget not found")
    session.delete(budget)
    return {"deleted": budget_id}