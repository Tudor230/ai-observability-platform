"""OTLP trace ingest endpoint (POST /api/v1/traces)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ...ingest import decode_trace_export
from ...ingest.pipeline import process_trace_batch
from ...models import Project
from ..deps import get_db, get_project_from_headers

router = APIRouter(tags=["ingest"])


@router.post("/traces")
async def ingest_traces(
    request: Request,
    session: Session = Depends(get_db),
    project: Project = Depends(get_project_from_headers),
) -> dict:
    body = await request.body()
    if not body:
        return {"ingested": 0, "detail": "empty body"}
    raw_spans = decode_trace_export(body)
    summaries = process_trace_batch(session, project, raw_spans)
    return {"ingested": len(summaries), "traces": summaries}