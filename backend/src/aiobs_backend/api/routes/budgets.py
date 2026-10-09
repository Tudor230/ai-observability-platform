"""Budgets: scoped CRUD (admin/exec + covering managers) + a status view.

Authorization model (audit item 5): admin key/admin session and `exec` manage
any budget; managers manage budgets whose department/team/project scope they
cover. Manager-created budgets must carry one of those scopes — client and
workflow are additional filters. Global (unscoped) budgets stay exec/admin-only.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...alerts import budget_spend, budget_window
from ...models import Budget, Client, Department, Project, Team
from ..deps import AccessScope, get_db, require_access
from ..memberships import approved_memberships, covers_scope
from ..queries import budget_scope_clause

router = APIRouter(tags=["budgets"])


class BudgetIn(BaseModel):
    name: str | None = None
    amount: float = Field(gt=0)
    period: date  # period anchor (day); the current window is derived from it
    period_type: str = Field(default="month", pattern="^(day|week|month)$")
    project: str | None = None  # external project_id
    client: str | None = None  # external client key
    workflow_name: str | None = None
    department: str | None = None  # internal department id
    team: str | None = None  # internal team id


class BudgetPatch(BaseModel):
    name: str | None = None
    amount: float | None = Field(default=None, gt=0)
    period: date | None = None
    period_type: str | None = Field(default=None, pattern="^(day|week|month)$")
    project: str | None = None
    client: str | None = None
    workflow_name: str | None = None
    department: str | None = None
    team: str | None = None


def _resolve_scope_fields(
    session: Session,
    project: str | None,
    client: str | None,
    department: str | None,
    team: str | None,
) -> dict[str, str | None]:
    """Resolve request scope fields to internal ids; 400 on unknown values."""
    project_db = None
    if project:
        project_db = session.execute(
            select(Project.id).where(Project.project_id == project)
        ).scalar_one_or_none()
        if project_db is None:
            raise HTTPException(status_code=400, detail=f"unknown project {project}")
    client_id = None
    if client:
        client_id = session.execute(
            select(Client.id).where(Client.external_key == client)
        ).scalar_one_or_none()
        if client_id is None:
            raise HTTPException(status_code=400, detail=f"unknown client {client}")
    department_id = None
    if department:
        department_id = session.execute(
            select(Department.id).where(Department.id == department)
        ).scalar_one_or_none()
        if department_id is None:
            raise HTTPException(status_code=400, detail="unknown department")
    team_id = None
    if team:
        team_id = session.execute(
            select(Team.id).where(Team.id == team)
        ).scalar_one_or_none()
        if team_id is None:
            raise HTTPException(status_code=400, detail="unknown team")
    return {
        "project_id": project_db,
        "client_id": client_id,
        "department_id": department_id,
        "team_id": team_id,
    }


def _caller_memberships(session: Session, access: AccessScope):
    if access.user is None:
        return []
    return approved_memberships(session, access.user.id)


def _is_unrestricted(access: AccessScope) -> bool:
    """Admin key/session, or any global grant (exec): every budget is fair game."""
    return access.unrestricted or access.project_ids is None


def _covers_target(
    session: Session,
    memberships,
    *,
    department_id: str | None,
    team_id: str | None,
    project_db_id: str | None,
) -> bool:
    if department_id and covers_scope(session, memberships, "department", department_id):
        return True
    if team_id and covers_scope(session, memberships, "team", team_id):
        return True
    if project_db_id and covers_scope(session, memberships, "project", project_db_id):
        return True
    return False


def _assert_can_write(
    session: Session,
    access: AccessScope,
    *,
    department_id: str | None,
    team_id: str | None,
    project_db_id: str | None,
) -> None:
    if _is_unrestricted(access):
        return
    if not any((department_id, team_id, project_db_id)):
        raise HTTPException(
            status_code=403,
            detail="a department, team or project scope is required",
        )
    memberships = _caller_memberships(session, access)
    if not _covers_target(
        session,
        memberships,
        department_id=department_id,
        team_id=team_id,
        project_db_id=project_db_id,
    ):
        raise HTTPException(status_code=403, detail="you do not manage this scope")


def _can_manage_budget(session: Session, access: AccessScope, budget: Budget) -> bool:
    if _is_unrestricted(access):
        return True
    return _covers_target(
        session,
        _caller_memberships(session, access),
        department_id=budget.department_id,
        team_id=budget.team_id,
        project_db_id=budget.project_id,
    )


def _name_maps(session: Session):
    projects = {
        pid: ext for pid, ext in session.execute(select(Project.id, Project.project_id))
    }
    clients = {
        cid: ext for cid, ext in session.execute(select(Client.id, Client.external_key))
    }
    departments = {
        d.id: d.name for d in session.execute(select(Department)).scalars()
    }
    teams = {t.id: t.name for t in session.execute(select(Team)).scalars()}
    return projects, clients, departments, teams


def _scope_label(budget: Budget) -> str:
    if budget.department_id:
        return "department"
    if budget.team_id:
        return "team"
    if budget.project_id:
        return "project"
    if budget.client_id:
        return "client"
    if budget.workflow_name:
        return "workflow"
    return "global"


def _budget_item(session: Session, budget: Budget, maps=None) -> dict:
    projects, clients, departments, teams = maps or _name_maps(session)
    return {
        "id": budget.id,
        "name": budget.name,
        "amount": float(budget.amount),
        "period": budget.period.isoformat(),
        "period_type": budget.period_type or "month",
        # External/internal labels, consistent with every other resource (F32).
        "project": projects.get(budget.project_id),
        "client": clients.get(budget.client_id),
        "workflow_name": budget.workflow_name,
        "department": departments.get(budget.department_id),
        "team": teams.get(budget.team_id),
        "scope": _scope_label(budget),
    }


def _scoped_budget_rows(session: Session, access: AccessScope):
    clause = budget_scope_clause(
        access.project_ids, access.department_ids, access.team_ids
    )
    stmt = select(Budget)
    if clause is not None:
        stmt = stmt.where(clause)
    return session.execute(stmt.order_by(Budget.period.desc())).scalars().all()


@router.get("/budgets")
def list_budgets(
    session: Session = Depends(get_db),
    access: AccessScope = Depends(require_access("manager", "exec")),
) -> dict:
    maps = _name_maps(session)
    items = [_budget_item(session, b, maps) for b in _scoped_budget_rows(session, access)]
    return {"items": items, "total": len(items)}


@router.post("/budgets")
def create_budget(
    body: BudgetIn,
    session: Session = Depends(get_db),
    access: AccessScope = Depends(require_access("manager", "exec")),
) -> dict:
    ids = _resolve_scope_fields(
        session, body.project, body.client, body.department, body.team
    )
    _assert_can_write(
        session,
        access,
        department_id=ids["department_id"],
        team_id=ids["team_id"],
        project_db_id=ids["project_id"],
    )
    period = datetime.combine(body.period, time.min, tzinfo=timezone.utc)
    budget = Budget(
        name=body.name,
        amount=body.amount,
        period=period,
        period_type=body.period_type,
        workflow_name=body.workflow_name,
        **ids,
    )
    session.add(budget)
    session.flush()
    session.commit()
    return _budget_item(session, budget)


@router.patch("/budgets/{budget_id}")
def update_budget(
    budget_id: str,
    body: BudgetPatch,
    session: Session = Depends(get_db),
    access: AccessScope = Depends(require_access("manager", "exec")),
) -> dict:
    budget = session.execute(
        select(Budget).where(Budget.id == budget_id)
    ).scalar_one_or_none()
    if budget is None:
        raise HTTPException(status_code=404, detail="budget not found")
    if not _can_manage_budget(session, access, budget):
        raise HTTPException(status_code=403, detail="you do not manage this scope")

    fields = body.model_dump(exclude_unset=True)
    provided = {key for key in fields if key in {"project", "client", "department", "team"}}
    resolved = _resolve_scope_fields(
        session,
        fields.get("project"),
        fields.get("client"),
        fields.get("department"),
        fields.get("team"),
    )
    # Validate the *resulting* scope before mutating (yield-dependency teardown
    # may commit on HTTPException otherwise).
    target = {
        "project_id": resolved["project_id"] if "project" in provided else budget.project_id,
        "client_id": resolved["client_id"] if "client" in provided else budget.client_id,
        "department_id": resolved["department_id"] if "department" in provided else budget.department_id,
        "team_id": resolved["team_id"] if "team" in provided else budget.team_id,
    }

    if not _is_unrestricted(access):
        if not any((target["department_id"], target["team_id"], target["project_id"])):
            raise HTTPException(
                status_code=403, detail="a department, team or project scope is required"
            )
        if not _covers_target(
            session,
            _caller_memberships(session, access),
            department_id=target["department_id"],
            team_id=target["team_id"],
            project_db_id=target["project_id"],
        ):
            raise HTTPException(status_code=403, detail="you do not manage this scope")

    if "name" in fields:
        budget.name = fields["name"]
    if "amount" in fields and body.amount is not None:
        budget.amount = Decimal(str(body.amount))
    if "period" in fields and body.period is not None:
        budget.period = datetime.combine(body.period, time.min, tzinfo=timezone.utc)
    if "period_type" in fields and body.period_type is not None:
        budget.period_type = body.period_type
    if "workflow_name" in fields:
        budget.workflow_name = fields["workflow_name"]
    budget.project_id = target["project_id"]
    budget.client_id = target["client_id"]
    budget.department_id = target["department_id"]
    budget.team_id = target["team_id"]
    session.flush()
    session.commit()
    return _budget_item(session, budget)


@router.delete("/budgets/{budget_id}")
def delete_budget(
    budget_id: str,
    session: Session = Depends(get_db),
    access: AccessScope = Depends(require_access("manager", "exec")),
) -> dict:
    budget = session.execute(
        select(Budget).where(Budget.id == budget_id)
    ).scalar_one_or_none()
    if budget is None:
        raise HTTPException(status_code=404, detail="budget not found")
    if not _can_manage_budget(session, access, budget):
        raise HTTPException(status_code=403, detail="you do not manage this scope")
    session.delete(budget)
    session.commit()
    return {"deleted": budget_id}


@router.get("/budgets/status")
def budget_status(
    session: Session = Depends(get_db),
    access: AccessScope = Depends(require_access("manager", "exec")),
) -> dict:
    """Read-only budget utilization for dashboards (no admin key needed).

    ``utilization`` is the true ratio (can exceed 1.0); clients must clamp only
    the bar width, never the number (F23). Budgets are scoped by their project,
    team or department; global budgets are exec/admin-only (ADR-0006).
    """
    maps = _name_maps(session)
    items = []
    for b in _scoped_budget_rows(session, access):
        spend = budget_spend(session, b)
        amount = float(b.amount or Decimal("0"))
        window_start, window_end = budget_window(b)
        item = _budget_item(session, b, maps)
        item.update(
            {
                "spend": round(spend, 6),
                "utilization": round(spend / amount, 4) if amount else 0.0,
                "period_start": window_start.isoformat(),
                "period_end": window_end.isoformat(),
            }
        )
        items.append(item)
    return {"items": items, "total": len(items)}
