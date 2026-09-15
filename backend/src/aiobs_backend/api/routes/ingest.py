"""OTLP trace ingest (POST /api/v1/traces and the standard OTLP path /v1/traces)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ...config import get_settings
from ...ingest import InvalidOtlpPayload, decode_trace_export
from ...ingest.pipeline import process_trace_batch
from ...models import Project
from ..deps import get_db, get_project_from_headers

router = APIRouter(tags=["ingest"])


async def _ingest(request: Request, session: Session, project: Project) -> dict:
    body = await request.body()
    if not body:
        return {"ingested": 0, "detail": "empty body"}
    max_bytes = get_settings().max_ingest_bytes
    if len(body) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"payload exceeds {max_bytes} bytes",
        )
    try:
        raw_spans = decode_trace_export(body)
    except InvalidOtlpPayload as exc:
        raise HTTPException(status_code=400, detail=f"invalid OTLP payload: {exc}") from exc
    summaries = process_trace_batch(session, project, raw_spans)
    return {"ingested": len(summaries), "traces": summaries}


@router.post("/traces")
async def ingest_traces(
    request: Request,
    session: Session = Depends(get_db),
    project: Project = Depends(get_project_from_headers),
) -> dict:
    return await _ingest(request, session, project)


# Standard OTLP HTTP path so the SDK exporter can point straight at the backend.
otlp_router = APIRouter(prefix="/v1", tags=["ingest"])


@otlp_router.post("/traces")
async def ingest_traces_otlp(
    request: Request,
    session: Session = Depends(get_db),
    project: Project = Depends(get_project_from_headers),
) -> dict:
    return await _ingest(request, session, project)