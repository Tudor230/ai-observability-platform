"""Metadata redaction + JSONB storage (F19)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from helpers import build_request, build_span

KEY = "test-key"


def _headers() -> dict:
    return {"x-project-name": "proj-1", "authorization": f"Bearer {KEY}"}


def test_metadata_is_redacted_before_persistence(client, session_factory, project):
    now = datetime.now(timezone.utc)
    metadata = (
        '{"ticket_id": "T-1", "api_key": "sk-secret", '
        '"nested": {"password": "hunter2", "note": "keep"}}'
    )
    root = build_span(
        name="checkout", oi_kind="CHAIN", span_id=1, trace_id=1500,
        start=now, end=now + timedelta(seconds=1),
        attrs={"sdk.project_id": "proj-1", "sdk.client_id": "client-42",
               "metadata": metadata},
    )
    resp = client.post("/api/v1/traces", content=build_request([root]), headers=_headers())
    assert resp.status_code == 200

    execution_id = client.get("/api/v1/executions").json()["items"][0]["id"]
    md = client.get(f"/api/v1/executions/{execution_id}").json()["metadata"]
    assert md["ticket_id"] == "T-1"
    assert md["api_key"] == "[redacted]"
    assert md["nested"]["password"] == "[redacted]"
    assert md["nested"]["note"] == "keep"

    with session_factory() as session:
        data_type = session.execute(
            text(
                "select data_type from information_schema.columns "
                "where table_name='executions' and column_name='metadata_json'"
            )
        ).scalar_one()
    assert data_type == "jsonb"
