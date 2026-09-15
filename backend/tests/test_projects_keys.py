"""Project key lifecycle (F18): rotate / disable / enable."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from helpers import build_request, build_span

ADMIN = {"x-admin-key": "admin"}


def _headers(project: str, key: str) -> dict:
    return {"x-project-name": project, "authorization": f"Bearer {key}"}


def _trace(trace_id: int, project_id: str):
    now = datetime.now(timezone.utc)
    return [
        build_span(
            name="checkout", oi_kind="CHAIN", span_id=1, trace_id=trace_id,
            start=now, end=now + timedelta(seconds=1),
            attrs={"sdk.project_id": project_id, "sdk.client_id": "client-42"},
        )
    ]


def test_disable_and_enable_project(client, project):
    created = client.post(
        "/api/v1/projects", json={"project_id": "proj-x", "name": "X"}, headers=ADMIN
    )
    assert created.status_code == 200, created.text
    key = created.json()["api_key"]

    ok = client.post("/api/v1/traces", content=build_request(_trace(901, "proj-x")), headers=_headers("proj-x", key))
    assert ok.status_code == 200

    disabled = client.post("/api/v1/projects/proj-x/disable", headers=ADMIN)
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    assert disabled.json()["revoked_at"]

    blocked = client.post("/api/v1/traces", content=build_request(_trace(902, "proj-x")), headers=_headers("proj-x", key))
    assert blocked.status_code == 403

    enabled = client.post("/api/v1/projects/proj-x/enable", headers=ADMIN)
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True
    assert enabled.json()["revoked_at"] is None

    again = client.post("/api/v1/traces", content=build_request(_trace(903, "proj-x")), headers=_headers("proj-x", key))
    assert again.status_code == 200


def test_rotate_invalidates_previous_key(client, project):
    created = client.post(
        "/api/v1/projects", json={"project_id": "proj-y", "name": "Y"}, headers=ADMIN
    ).json()
    rotated = client.post("/api/v1/projects/proj-y/rotate", headers=ADMIN).json()

    old = client.post(
        "/api/v1/traces", content=build_request(_trace(904, "proj-y")),
        headers=_headers("proj-y", created["api_key"]),
    )
    assert old.status_code == 401
    new = client.post(
        "/api/v1/traces", content=build_request(_trace(905, "proj-y")),
        headers=_headers("proj-y", rotated["api_key"]),
    )
    assert new.status_code == 200
