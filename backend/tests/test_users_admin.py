"""Admin accounts: provisioning, password resets, direct membership grants."""
from __future__ import annotations

from helpers import seed_team, seed_user

ADMIN = {"x-admin-key": "admin"}


def test_reset_password_revokes_sessions(anon, client, session_factory):
    created = client.post("/api/v1/users", json={"email": "u@x"}, headers=ADMIN).json()
    assert created["password"]
    assert (
        anon.post(
            "/api/v1/auth/login",
            json={"email": "u@x", "password": created["password"]},
        ).status_code
        == 200
    )
    assert anon.get("/api/v1/auth/me").status_code == 200

    reset = client.post(f"/api/v1/users/{created['id']}/reset-password", headers=ADMIN)
    assert reset.status_code == 200
    new_password = reset.json()["password"]
    assert new_password != created["password"]

    # The old session and the old password are both dead.
    assert anon.get("/api/v1/auth/me").status_code == 401
    assert (
        anon.post(
            "/api/v1/auth/login",
            json={"email": "u@x", "password": created["password"]},
        ).status_code
        == 401
    )
    assert (
        anon.post(
            "/api/v1/auth/login", json={"email": "u@x", "password": new_password}
        ).status_code
        == 200
    )


def test_admin_grants_and_revokes_memberships(app, anon, client, session_factory):
    with session_factory() as session:
        team = seed_team(session, name="Core")
        user, user_key = seed_user(session, "dev@x")
        session.commit()
        team_id, user_id = team.id, user.id

    user_headers = {"x-api-key": user_key}
    # No memberships yet: reads are forbidden.
    assert anon.get("/api/v1/executions", headers=user_headers).status_code == 403

    granted = client.post(
        f"/api/v1/users/{user_id}/memberships",
        json={"role": "engineer", "scope_type": "team", "scope_id": team_id},
        headers=ADMIN,
    )
    assert granted.status_code == 200, granted.text
    assert granted.json()["scope_name"] == "Core"
    assert anon.get("/api/v1/executions", headers=user_headers).status_code == 200

    # Duplicate active grants and invalid role/scope pairs are rejected.
    duplicate = client.post(
        f"/api/v1/users/{user_id}/memberships",
        json={"role": "engineer", "scope_type": "team", "scope_id": team_id},
        headers=ADMIN,
    )
    assert duplicate.status_code == 409
    invalid = client.post(
        f"/api/v1/users/{user_id}/memberships",
        json={"role": "client", "scope_type": "team", "scope_id": team_id},
        headers=ADMIN,
    )
    assert invalid.status_code == 422

    listed = client.get("/api/v1/users", headers=ADMIN).json()["items"]
    row = next(item for item in listed if item["id"] == user_id)
    assert row["roles"] == ["engineer"]
    membership_id = row["memberships"][0]["id"]

    revoked = client.delete(
        f"/api/v1/users/{user_id}/memberships/{membership_id}", headers=ADMIN
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    assert anon.get("/api/v1/executions", headers=user_headers).status_code == 403
