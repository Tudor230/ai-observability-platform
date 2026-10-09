"""Alerts: scoped list (filterable, searchable, sortable) + scoped ack.

Acknowledge/close is allowed for the admin key/admin session, any global grant
(exec), and managers covering the alert's scope — a budget's project/team/
department or a rule's org scope. Global alerts stay exec/admin-only.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session

from ...models import Alert, AlertRule, Budget
from ..deps import AccessScope, get_db, require_access
from ..memberships import approved_memberships, covers_scope, scope_name
from ..queries import alert_scope_clause

router = APIRouter(tags=["alerts"])

AlertSort = Literal["triggered_at", "severity"]


def _sort_clause(sort: str, order: str):
    col = Alert.triggered_at if sort == "triggered_at" else Alert.severity
    order_fn = asc if order == "asc" else desc
    return order_fn(col), order_fn(Alert.id)


def _is_unrestricted(access: AccessScope) -> bool:
    return access.unrestricted or access.project_ids is None


def _alert_scope(session: Session, alert: Alert) -> tuple[str, str | None]:
    """(scope_type, scope_id) of the thing the alert is about."""
    if alert.dimension == "budget" and alert.dimension_key:
        budget = session.get(Budget, alert.dimension_key)
        if budget is None:
            return "global", None
        if budget.project_id:
            return "project", budget.project_id
        if budget.team_id:
            return "team", budget.team_id
        if budget.department_id:
            return "department", budget.department_id
        return "global", None
    if alert.rule_ref:
        rule = session.get(AlertRule, alert.rule_ref)
        if rule is not None:
            return rule.scope_type, rule.scope_id
    return "global", None


def _can_ack(session: Session, access: AccessScope, alert: Alert) -> bool:
    if _is_unrestricted(access):
        return True
    if access.user is None:
        return False
    scope_type, scope_id = _alert_scope(session, alert)
    if scope_type == "global" or not scope_id:
        return False
    memberships = approved_memberships(session, access.user.id)
    return covers_scope(session, memberships, scope_type, scope_id)


def _alert_item(session: Session, access: AccessScope, alert: Alert) -> dict:
    scope_type, scope_id = _alert_scope(session, alert)
    return {
        "id": alert.id,
        "rule_id": alert.rule_id,
        "rule_ref": alert.rule_ref,
        "severity": alert.severity,
        "message": alert.message,
        "dimension": alert.dimension,
        "dimension_key": alert.dimension_key,
        "status": alert.status,
        "triggered_at": alert.triggered_at.isoformat() if alert.triggered_at else None,
        "scope": scope_type,
        "scope_name": scope_name(session, scope_type, scope_id),
        "can_ack": _can_ack(session, access, alert),
    }


@router.get("/alerts")
def list_alerts(
    session: Session = Depends(get_db),
    status: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    sort: AlertSort = Query(default="triggered_at"),
    order: Literal["asc", "desc"] = Query(default="desc"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    access: AccessScope = Depends(require_access()),
) -> dict:
    scope_clause = alert_scope_clause(
        access.resolve_project_filter(None), access.department_ids, access.team_ids
    )

    def _apply_filters(query):
        if scope_clause is not None:
            query = query.where(scope_clause)
        if status:
            query = query.where(Alert.status == status)
        if severity:
            query = query.where(Alert.severity == severity)
        if q:
            query = query.where(Alert.message.ilike(f"%{q}%"))
        return query

    stmt = _apply_filters(select(Alert))
    count_stmt = _apply_filters(select(func.count()).select_from(Alert))
    rows = session.execute(
        stmt.order_by(*_sort_clause(sort, order)).limit(limit).offset(offset)
    ).scalars().all()
    total = session.execute(count_stmt).scalar_one()
    items = [_alert_item(session, access, a) for a in rows]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.patch("/alerts/{alert_id}")
def update_alert_status(
    alert_id: str,
    status: str = Query(...),
    session: Session = Depends(get_db),
    access: AccessScope = Depends(require_access()),
) -> dict:
    if status not in {"open", "acknowledged", "closed"}:
        raise HTTPException(status_code=400, detail="invalid status")
    alert = session.execute(
        select(Alert).where(Alert.id == alert_id)
    ).scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    if not _can_ack(session, access, alert):
        raise HTTPException(status_code=403, detail="you do not manage this alert's scope")
    alert.status = status
    session.flush()
    session.commit()
    return {"id": alert.id, "status": alert.status}
