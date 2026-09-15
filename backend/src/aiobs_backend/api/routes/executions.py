"""Executions: list (paginated, filtered), detail, span list, failure tree."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...models import Client, Execution, Project, Span
from ..deps import get_db, get_project_scope, require_read_access
from ..queries import exec_rows, parse_dt
from ..serialize import execution_dict, span_dict

router = APIRouter(tags=["executions"], dependencies=[Depends(require_read_access)])


def _scoped_execution(
    session: Session, execution_id: str, project_scope: str | None
) -> Execution:
    """Load an execution, hiding rows outside the caller's project scope (F07)."""
    row = session.execute(
        select(Execution).where(Execution.id == execution_id)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="execution not found")
    if project_scope:
        project_ext = session.execute(
            select(Project.project_id).where(Project.id == row.project_id)
        ).scalar_one_or_none()
        if project_ext != project_scope:
            raise HTTPException(status_code=404, detail="execution not found")
    return row


@router.get("/executions")
def list_executions(
    session: Session = Depends(get_db),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    days: int | None = Query(default=None, ge=1, le=3650),
    project_id: str | None = Query(default=None),
    client_id: str | None = Query(default=None),
    workflow: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    project_scope: str | None = Depends(get_project_scope),
) -> dict:
    # `days` is a relative window; explicit start/end win when both are given (F15).
    start_dt = parse_dt(start)
    if start_dt is None and days is not None:
        start_dt = datetime.now(timezone.utc) - timedelta(days=days)
    base = exec_rows(
        session,
        start=start_dt,
        end=parse_dt(end, end_of_day=True),
        project_id=project_id or project_scope,
        client_id=client_id,
        workflow=workflow,
        status=status,
    )
    total = session.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar_one()
    rows = session.execute(base.limit(limit).offset(offset)).all()
    items = [execution_dict(ex, project_ext, client_ext) for ex, project_ext, client_ext in rows]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/executions/{execution_id}")
def get_execution(
    execution_id: str,
    session: Session = Depends(get_db),
    project_scope: str | None = Depends(get_project_scope),
) -> dict:
    row = _scoped_execution(session, execution_id, project_scope)
    project_ext = session.execute(
        select(Project.project_id).where(Project.id == row.project_id)
    ).scalar_one_or_none()
    client_ext = None
    if row.client_id:
        client_ext = session.execute(
            select(Client.external_key).where(Client.id == row.client_id)
        ).scalar_one_or_none()
    return execution_dict(row, project_ext, client_ext)


@router.get("/executions/{execution_id}/spans")
def get_spans(
    execution_id: str,
    session: Session = Depends(get_db),
    project_scope: str | None = Depends(get_project_scope),
) -> dict:
    _scoped_execution(session, execution_id, project_scope)
    spans = session.execute(
        select(Span)
        .where(Span.execution_id == execution_id)
        .order_by(Span.started_at)
    ).scalars().all()
    return {"items": [span_dict(s) for s in spans], "total": len(spans)}


@router.get("/executions/{execution_id}/failures")
def get_failure_tree(
    execution_id: str,
    session: Session = Depends(get_db),
    project_scope: str | None = Depends(get_project_scope),
) -> dict:
    """Failure tree: failing spans + parent/child relationships + root cause."""
    _scoped_execution(session, execution_id, project_scope)
    spans = session.execute(
        select(Span).where(Span.execution_id == execution_id)
    ).scalars().all()
    failing = [s for s in spans if s.status == "error" or s.error_kind]
    nodes = [
        {
            "span_id": s.span_id,
            "parent_id": s.parent_id,
            "kind": s.kind,
            "name": s.name,
            "status": s.status,
            "error_kind": s.error_kind,
            "error_type": s.error_type,
            "error_message": s.error_message,
            "started_at": s.started_at.isoformat() if s.started_at else None,
        }
        for s in failing
    ]
    return {
        "execution_id": execution_id,
        "error_count": len(failing),
        "nodes": sorted(nodes, key=lambda n: n["started_at"] or ""),
    }