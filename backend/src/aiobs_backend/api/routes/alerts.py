"""Alerts: list + status management."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...models import Alert
from ..deps import get_admin_key, get_db

router = APIRouter(tags=["alerts"])


@router.get("/alerts")
def list_alerts(
    session: Session = Depends(get_db),
    status: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    stmt = select(Alert)
    if status:
        stmt = stmt.where(Alert.status == status)
    if severity:
        stmt = stmt.where(Alert.severity == severity)
    rows = session.execute(
        stmt.order_by(Alert.triggered_at.desc()).limit(limit).offset(offset)
    ).scalars().all()
    count_stmt = select(func.count()).select_from(Alert)
    if status:
        count_stmt = count_stmt.where(Alert.status == status)
    if severity:
        count_stmt = count_stmt.where(Alert.severity == severity)
    total = session.execute(count_stmt).scalar_one()
    items = [
        {
            "id": a.id,
            "rule_id": a.rule_id,
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
    return {"id": alert.id, "status": alert.status}