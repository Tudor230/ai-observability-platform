"""Maintenance endpoints: on-demand analytics rollup and alert evaluation."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...alerts import evaluate_alerts
from ...analytics import rollup_recent
from ..deps import get_admin_key, get_db

router = APIRouter(tags=["maintenance"], dependencies=[Depends(get_admin_key)])


@router.post("/metrics/rollup")
def rollup(session: Session = Depends(get_db)) -> dict:
    counts = rollup_recent(session)
    return {"days": len(counts), "metrics_written": sum(counts.values())}


@router.post("/alerts/evaluate")
def evaluate(session: Session = Depends(get_db)) -> dict:
    created = evaluate_alerts(session)
    return {"created": len(created), "alerts": created}