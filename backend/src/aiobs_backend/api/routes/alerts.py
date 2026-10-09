"""Alerts: list (filterable, searchable, sortable) + status management."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session

from ...models import Alert
from ..deps import AccessScope, get_admin_key, get_db, require_access
from ..queries import alert_scope_clause

router = APIRouter(tags=["alerts"])

AlertSort = Literal["triggered_at", "severity"]


def _sort_clause(sort: str, order: str):
    col = Alert.triggered_at if sort == "triggered_at" else Alert.severity
    order_fn = asc if order == "asc" else desc
    return order_fn(col), order_fn(Alert.id)


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
    # Rule alerts are global; budget alerts follow their budget's project.
    scope_clause = alert_scope_clause(access.resolve_project_filter(None))

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
    items = [
        {
            "id": a.id,
            "rule_id": a.rule_id,
            "rule_ref": a.rule_ref,
            "severity": a.severity,
            "message": a.message,
            "dimension": a.dimension,
            "dimension_key": a.dimension_key,
            "status": a.status,
            "triggered_at": a.triggered_at.isoformat() if a.triggered_at else None,
        }
        for a in rows
    ]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.patch("/alerts/{alert_id}", dependencies=[Depends(get_admin_key)])
def update_alert_status(
    alert_id: str, status: str = Query(...), session: Session = Depends(get_db)
) -> dict:
    if status not in {"open", "acknowledged", "closed"}:
        raise HTTPException(status_code=400, detail="invalid status")
    alert = session.execute(
        select(Alert).where(Alert.id == alert_id)
    ).scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    alert.status = status
    session.flush()
    session.commit()
    return {"id": alert.id, "status": alert.status}