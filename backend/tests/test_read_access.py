"""Read access (F06) and project-scope enforcement (F07)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from helpers import build_request, build_span, seed_project

from aiobs_backend.config import get_settings

KEY = "test-key"


def _headers(project: str = "proj-1") -> dict:
    return {"x-project-name": project, "authorization": f"Bearer {KEY}"}


def _trace(trace_id: int, project_id: str = "proj-1"):
    now = datetime.now(timezone.utc)
    return [
        build_span(
            name="checkout", oi_kind="CHAIN", span_id=1, trace_id=trace_id,
            start=now, end=now + timedelta(seconds=1),
            attrs={"sdk.project_id": project_id, "sdk.client_id": "client-42"},
        )
    ]


def test_unknown_project_scope_is_rejected(client, project):
    resp = client.get("/api/v1/executions", headers={"x-project-name": "nope"})
    assert resp.status_code == 404


def test_scoped_detail_is_isolated(client, session_factory, project):
    client.post("/api/v1/traces", content=build_request(_trace(1200)), headers=_headers())
    with session_factory() as session:
        seed_project(session, project_id="proj-2", api_key="k2", name="P2")
        session.commit()

    execution_id = client.get("/api/v1/executions").json()["items"][0]["id"]
    other = {"x-project-name": "proj-2"}

    assert client.get(f"/api/v1/executions/{execution_id}", headers=other).status_code == 404
    assert client.get(f"/api/v1/executions/{execution_id}/spans", headers=other).status_code == 404
    assert client.get(f"/api/v1/executions/{execution_id}/failures", headers=other).status_code == 404
    assert client.get(
        f"/api/v1/executions/{execution_id}", headers={"x-project-name": "proj-1"}
    ).status_code == 200
    assert client.get(f"/api/v1/executions/{execution_id}").status_code == 200


def test_read_auth_when_configured(client, project, monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("AIOBS_READ_API_KEY", "read-secret")
    get_settings.cache_clear()
    try:
        assert client.get("/api/v1/executions").status_code == 401
        assert client.get("/api/v1/executions", headers={"x-api-key": "wrong"}).status_code == 401
        assert client.get(
            "/api/v1/executions", headers={"x-api-key": "read-secret"}
        ).status_code == 200
        assert client.get(
            "/api/v1/executions", headers={"x-admin-key": "admin"}
        ).status_code == 200
    finally:
        monkeypatch.delenv("AIOBS_READ_API_KEY", raising=False)
        get_settings.cache_clear()
