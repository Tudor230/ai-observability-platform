"""Membership RBAC (ADR-0006): roles, user API keys, admin gates."""
from __future__ import annotations

from helpers import seed_user

ADMIN = {"x-admin-key": "admin"}


def test_users_require_admin(anon):
    assert anon.post("/api/v1/users", json={"email": "x@y.z"}).status_code == 401


def test_reads_require_auth(anon, project):
    assert anon.get("/api/v1/executions").status_code == 401
    assert anon.get("/api/v1/overview").status_code == 401
    assert anon.get("/api/v1/costs").status_code == 401


def test_role_gated_reads(anon, client, session_factory, project):
    with session_factory() as session:
        eng, eng_key = seed_user(
            session, "eng@x", role="engineer", scope_type="team", scope_id=project.team_id
        )
        mgr, mgr_key = seed_user(
            session, "mgr@x", role="manager", scope_type="team", scope_id=project.team_id
        )
        session.commit()

    eng_h = {"x-api-key": eng_key}
    mgr_h = {"x-api-key": mgr_key}
    assert anon.get("/api/v1/executions", headers=eng_h).status_code == 200
    # Engineer cannot read cost views; manager can.
    assert anon.get("/api/v1/costs", headers=eng_h).status_code == 403
    assert anon.get("/api/v1/costs", headers=mgr_h).status_code == 200
    # Shared views accept any authenticated role.
    assert anon.get("/api/v1/overview", headers=eng_h).status_code == 200

    client.post(f"/api/v1/users/{eng.id}/disable")
    assert anon.get("/api/v1/executions", headers=eng_h).status_code == 401


def test_user_creation_mints_password_once(anon):
    created = anon.post(
        "/api/v1/users", json={"email": "new@x"}, headers=ADMIN
    ).json()
    assert created["password"]
    assert created["api_key"]

    explicit = anon.post(
        "/api/v1/users",
        json={"email": "pw@x", "password": "chosen-pass-1"},
        headers=ADMIN,
    ).json()
    assert explicit["password"] == "chosen-pass-1"


def test_duplicate_email_conflicts(anon):
    anon.post("/api/v1/users", json={"email": "dup@x"}, headers=ADMIN)
    assert (
        anon.post("/api/v1/users", json={"email": "dup@x"}, headers=ADMIN).status_code
        == 409
    )
