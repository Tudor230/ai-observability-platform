"""Requests & approvals: submit, guards, materialization, key minting (ADR-0006)."""
from __future__ import annotations

from fastapi.testclient import TestClient
from helpers import seed_department, seed_project, seed_team, seed_user

CSRF = {"x-requested-with": "aiobs"}


def _login(anon, email, password="test-pass-123"):
    resp = anon.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, resp.text


def _submit(anon, type_, payload):
    return anon.post(
        "/api/v1/requests", json={"type": type_, "payload": payload}, headers=CSRF
    )


def test_department_request_becomes_manager(anon, client, session_factory):
    with session_factory() as session:
        existing = seed_department(session, "Existing")
        seed_user(
            session,
            "founder@x",
            role="manager",
            scope_type="department",
            scope_id=existing.id,
        )
        session.commit()
    _login(anon, "founder@x")

    created = _submit(anon, "create_department", {"name": "Data"})
    assert created.status_code == 200, created.text
    # A manager may request a department but cannot approve one (admin/exec do).
    assert created.json()["status"] == "pending"
    request_id = created.json()["id"]

    approvals = client.get("/api/v1/requests?view=to_approve").json()
    assert approvals["pending_approvals"] == 1
    assert client.post(f"/api/v1/requests/{request_id}/approve").status_code == 200

    me = anon.get("/api/v1/auth/me").json()
    assert "manager" in me["roles"]
    assert any(m["scope_name"] == "Data" for m in me["memberships"])
    departments = client.get("/api/v1/departments").json()["items"]
    assert any(d["name"] == "Data" for d in departments)


def test_engineer_and_client_cannot_request_departments(app, session_factory):
    with session_factory() as session:
        department = seed_department(session, "Ops")
        team = seed_team(session, name="Core", department=department)
        project = seed_project(
            session, project_id="p1", api_key="k", name="P1", team=team
        )
        _, engineer_key = seed_user(
            session, "eng@x", role="engineer", scope_type="team", scope_id=team.id
        )
        _, client_key = seed_user(
            session,
            "cli@x",
            role="client",
            scope_type="project",
            scope_id=project.id,
        )
        session.commit()

    for key in (engineer_key, client_key):
        caller = TestClient(app, headers={"x-api-key": key})
        denied = caller.post(
            "/api/v1/requests",
            json={"type": "create_department", "payload": {"name": "Nope"}},
        )
        assert denied.status_code == 403, denied.text
        # Other request types are unaffected.
        assert caller.get("/api/v1/requests").status_code == 200


def test_request_lifecycle_guards(anon, client, session_factory):
    with session_factory() as session:
        existing = seed_department(session, "Existing")
        seed_user(
            session,
            "dev@x",
            role="manager",
            scope_type="department",
            scope_id=existing.id,
        )
        session.commit()
    _login(anon, "dev@x")

    first = _submit(anon, "create_department", {"name": "X"})
    assert first.status_code == 200
    # Identical pending request: rejected as a duplicate.
    assert _submit(anon, "create_department", {"name": "X"}).status_code == 409
    request_id = first.json()["id"]

    cancelled = anon.post(f"/api/v1/requests/{request_id}/cancel", headers=CSRF)
    assert cancelled.status_code == 200
    resubmitted = _submit(anon, "create_department", {"name": "X"})
    assert resubmitted.status_code == 200
    new_id = resubmitted.json()["id"]

    assert client.post(f"/api/v1/requests/{new_id}/reject", json={}).status_code == 422
    rejected = client.post(
        f"/api/v1/requests/{new_id}/reject", json={"reason": "not now"}
    )
    assert rejected.status_code == 200
    assert rejected.json()["reason"] == "not now"
    # A decided request can no longer be approved.
    assert client.post(f"/api/v1/requests/{new_id}/approve").status_code == 409


def test_admin_department_request_is_auto_approved(anon, session_factory):
    with session_factory() as session:
        seed_user(session, "admin@x", role="admin", scope_type="global")
        session.commit()
    _login(anon, "admin@x")

    created = _submit(anon, "create_department", {"name": "Platform"})
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["status"] == "approved"
    assert body["approver_id"]  # self-approved

    me = anon.get("/api/v1/auth/me").json()
    assert any(m["scope_name"] == "Platform" for m in me["memberships"])
    assert (
        anon.get("/api/v1/requests?view=to_approve").json()["pending_approvals"] == 0
    )


def test_manager_creates_team_project_and_mints_key(anon, session_factory):
    with session_factory() as session:
        department = seed_department(session, "Ops")
        seed_user(
            session,
            "mgr@x",
            role="manager",
            scope_type="department",
            scope_id=department.id,
        )
        session.commit()
        department_id = department.id
    _login(anon, "mgr@x")

    # A covering manager self-approves: both requests are approved on submit.
    team_request = _submit(
        anon, "create_team", {"name": "Core", "department_id": department_id}
    )
    assert team_request.status_code == 200, team_request.text
    assert team_request.json()["status"] == "approved"

    teams = anon.get("/api/v1/teams").json()["items"]
    team_id = next(t["id"] for t in teams if t["name"] == "Core")

    project_request = _submit(
        anon,
        "create_project",
        {"project_id": "core-api", "name": "Core API", "team_id": team_id},
    )
    assert project_request.status_code == 200
    assert project_request.json()["status"] == "approved"

    listing = anon.get("/api/v1/projects").json()["items"]
    assert listing and listing[0]["project_id"] == "core-api"
    assert listing[0]["has_keys"] is False
    # No key exists yet: ingest is rejected until a member adds one (key-first, ADR-0008).
    blocked = anon.post(
        "/api/v1/traces",
        content=b"",
        headers={"x-project-name": "core-api", "authorization": "Bearer nope"},
    )
    assert blocked.status_code == 401
    assert "invalid API key" in blocked.json()["detail"]

    minted = anon.post(
        "/api/v1/projects/core-api/keys", json={"label": "demo"}, headers=CSRF
    )
    assert minted.status_code == 200
    assert minted.json()["api_key"].startswith("aiobs_")


def test_membership_flow_and_manager_grant_restriction(
    app, anon, client, session_factory
):
    with session_factory() as session:
        department = seed_department(session, "Ops")
        team = seed_team(session, name="Core", department=department)
        seed_project(session, project_id="p1", api_key="k", name="P1", team=team)
        _, mgr_key = seed_user(
            session, "mgr@x", role="manager", scope_type="team", scope_id=team.id
        )
        _, eng_key = seed_user(session, "eng@x")
        session.commit()
        team_id = team.id

    _login(anon, "eng@x")
    assert (
        anon.get("/api/v1/executions", headers={"x-api-key": eng_key}).status_code
        == 403
    )

    request = _submit(
        anon,
        "membership",
        {"role": "engineer", "scope_type": "team", "scope_id": team_id},
    )
    assert request.status_code == 200, request.text
    # A separate key-authenticated client: the engineer's session cookie must
    # not override the manager's identity.
    manager = TestClient(app, headers={"x-api-key": mgr_key})
    approved = manager.post(f"/api/v1/requests/{request.json()['id']}/approve")
    assert approved.status_code == 200
    assert (
        anon.get("/api/v1/executions", headers={"x-api-key": eng_key}).status_code
        == 200
    )

    # Manager grants are admin/exec-only even for a covering team manager.
    grant = _submit(
        anon,
        "membership",
        {"role": "manager", "scope_type": "team", "scope_id": team_id},
    )
    denied = manager.post(f"/api/v1/requests/{grant.json()['id']}/approve")
    assert denied.status_code == 403
    assert client.post(f"/api/v1/requests/{grant.json()['id']}/approve").status_code == 200


def test_membership_scope_must_match_role(anon, session_factory):
    with session_factory() as session:
        team = seed_team(session)
        seed_user(session, "dev@x")
        session.commit()
        team_id = team.id
    _login(anon, "dev@x")
    bad = _submit(
        anon,
        "membership",
        {"role": "client", "scope_type": "team", "scope_id": team_id},
    )
    assert bad.status_code == 422


def test_duplicate_membership_request_is_rejected(anon, session_factory):
    with session_factory() as session:
        team = seed_team(session)
        seed_user(
            session, "eng@x", role="engineer", scope_type="team", scope_id=team.id
        )
        session.commit()
        team_id = team.id
    _login(anon, "eng@x")

    duplicate = _submit(
        anon,
        "membership",
        {"role": "engineer", "scope_type": "team", "scope_id": team_id},
    )
    assert duplicate.status_code == 409, duplicate.text
    assert "already hold" in duplicate.json()["detail"]

    # A different role on the same scope is still requestable (upgrade path).
    upgrade = _submit(
        anon,
        "membership",
        {"role": "manager", "scope_type": "team", "scope_id": team_id},
    )
    assert upgrade.status_code == 200, upgrade.text
    assert upgrade.json()["status"] == "pending"


def test_non_covering_manager_cannot_approve(app, anon, client, session_factory):
    with session_factory() as session:
        department_a = seed_department(session, "A")
        department_b = seed_department(session, "B")
        _, mgr_key = seed_user(
            session,
            "mgr@x",
            role="manager",
            scope_type="department",
            scope_id=department_a.id,
        )
        seed_user(session, "dev@x")
        session.commit()
        department_b_id = department_b.id
    _login(anon, "dev@x")

    request = _submit(
        anon, "create_team", {"name": "T", "department_id": department_b_id}
    )
    manager = TestClient(app, headers={"x-api-key": mgr_key})
    denied = manager.post(f"/api/v1/requests/{request.json()['id']}/approve")
    assert denied.status_code == 403
    assert client.post(f"/api/v1/requests/{request.json()['id']}/approve").status_code == 200
