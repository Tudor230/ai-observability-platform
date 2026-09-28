"""Project key lifecycle (F18/ADR-0007): list, add, rotate, revoke, disable."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from helpers import build_request, build_span, seed_project, seed_user

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


def _ingest(client, project: str, key: str, trace_id: int) -> int:
    return client.post(
        "/api/v1/traces",
        content=build_request(_trace(trace_id, project)),
        headers=_headers(project, key),
    ).status_code


def test_disable_and_enable_project(client, project):
    created = client.post(
        "/api/v1/projects", json={"project_id": "proj-x", "name": "X"}, headers=ADMIN
    )
    assert created.status_code == 200, created.text
    key = created.json()["api_key"]

    assert _ingest(client, "proj-x", key, 901) == 200

    disabled = client.post("/api/v1/projects/proj-x/disable", headers=ADMIN)
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    assert disabled.json()["revoked_at"]

    assert _ingest(client, "proj-x", key, 902) == 403

    enabled = client.post("/api/v1/projects/proj-x/enable", headers=ADMIN)
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True
    assert enabled.json()["revoked_at"] is None

    assert _ingest(client, "proj-x", key, 903) == 200


def test_add_rotate_and_revoke_keys(client, project):
    created = client.post(
        "/api/v1/projects", json={"project_id": "proj-y", "name": "Y"}, headers=ADMIN
    ).json()

    keys = client.get("/api/v1/projects/proj-y/keys", headers=ADMIN).json()
    assert keys["total"] == 1
    first = keys["items"][0]
    assert first["active"] is True
    assert first["hint"].endswith(created["api_key"][-4:])
    assert created["api_key"] not in str(keys)  # only the redacted form is returned

    added = client.post(
        "/api/v1/projects/proj-y/keys", json={"label": "ci"}, headers=ADMIN
    ).json()
    assert added["label"] == "ci"
    assert client.get("/api/v1/projects/proj-y/keys", headers=ADMIN).json()["total"] == 2

    # Every active key authenticates against the same project.
    assert _ingest(client, "proj-y", created["api_key"], 910) == 200
    assert _ingest(client, "proj-y", added["api_key"], 911) == 200

    rotated = client.post(
        f"/api/v1/projects/proj-y/keys/{added['id']}/rotate", headers=ADMIN
    ).json()
    assert rotated["label"] == "ci"
    assert _ingest(client, "proj-y", added["api_key"], 912) == 401
    assert _ingest(client, "proj-y", rotated["api_key"], 913) == 200

    revoked = client.delete(
        f"/api/v1/projects/proj-y/keys/{first['id']}", headers=ADMIN
    )
    assert revoked.status_code == 200
    assert revoked.json()["active"] is False
    assert _ingest(client, "proj-y", created["api_key"], 914) == 401

    listed = client.get("/api/v1/projects/proj-y/keys", headers=ADMIN).json()["items"]
    first_after = next(item for item in listed if item["id"] == first["id"])
    assert first_after["active"] is False

    # A revoked key cannot be rotated.
    again = client.post(
        f"/api/v1/projects/proj-y/keys/{first['id']}/rotate", headers=ADMIN
    )
    assert again.status_code == 409


def test_covering_member_manages_keys(app, client, session_factory, project):
    with session_factory() as session:
        _, member_key = seed_user(
            session,
            "eng@x",
            role="engineer",
            scope_type="team",
            scope_id=project.team_id,
        )
        seed_project(session, project_id="proj-2", api_key="k2", name="P2")
        session.commit()

    member = TestClient(app, headers={"x-api-key": member_key})
    created = member.post(
        "/api/v1/projects/proj-1/keys", json={"label": "local"}
    ).json()
    assert created["api_key"].startswith("aiobs_")
    assert member.get("/api/v1/projects/proj-1/keys").status_code == 200
    assert _ingest(member, "proj-1", created["api_key"], 920) == 200

    # Out-of-scope projects are invisible to the member's key operations.
    assert member.get("/api/v1/projects/proj-2/keys").status_code == 404
    assert member.post("/api/v1/projects/proj-2/keys", json={}).status_code == 404
