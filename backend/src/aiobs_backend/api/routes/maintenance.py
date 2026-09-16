"""Maintenance endpoints: on-demand analytics rollup, alert evaluation, retention."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...alerts import evaluate_alerts
from ...analytics import rollup_recent
from ...config import get_settings
from ...retention import purge_expired
from ..deps import get_admin_key, get_db

router = APIRouter(tags=["maintenance"], dependencies=[Depends(get_admin_key)])


@router.post("/metrics/rollup")
def rollup(session: Session = Depends(get_db)) -> dict:
    counts = rollup_recent(session)
    session.commit()  # response is sent before dependency teardown (see ingest route)
    days = len({key.split(":", 1)[0] for key in counts})
    return {"days": days, "metrics_written": sum(counts.values())}


@router.post("/alerts/evaluate")
def evaluate(session: Session = Depends(get_db)) -> dict:
    created = evaluate_alerts(session)
    session.commit()
    return {"created": len(created), "alerts": created}


@router.post("/maintenance/purge")
def purge(session: Session = Depends(get_db)) -> dict:
    """Apply the configured retention window (F35); no-op when retention is 0."""
    result = purge_expired(session, get_settings().retention_days)
    session.commit()
    return result