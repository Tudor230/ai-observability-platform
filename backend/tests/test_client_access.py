"""Clients are outsiders: no self-service requests, no org directory (refinements v2)."""
from __future__ import annotations

from helpers import seed_department, seed_project, seed_team, seed_user


def _seed(session):
    department = seed_department(session, "Ops")
    team = seed_team(session, name="A", department=department)
    p1 = seed_project(session, project_id="p1", api_key="k1", name="P1", team=team)
    _, client_key = seed_user(
        session, "cli@x", role="client", scope_type="project", scope_id=p1.id
    )
    _, eng_key = seed_user(
        session, "eng@x", role="engineer", scope_type="team", scope_id=team.id
    )
    session.commit()
    return team.id, p1.id, client_key, eng_key


def test_clients_cannot_use_requests_or_directory(anon, session_factory):
    with session_factory() as session:
        team_id, project_id, client_key, _ = _seed(session)

    headers = {"x-api-key": client_key}
    assert anon.get("/api/v1/requests", headers=headers).status_code == 403
    membership = {
        "type": "membership",
        "payload": {"role": "engineer", "scope_type": "team", "scope_id": team_id},
    }
    assert (
        anon.post("/api/v1/requests", json=membership, headers=headers).status_code == 403
    )
    assert anon.get("/api/v1/departments", headers=headers).status_code == 403
    assert anon.get("/api/v1/teams", headers=headers).status_code == 403

    # The client still reads its own scoped executions (outsider, not blind).
    items = anon.get("/api/v1/executions", headers=headers).json()["items"]
    assert items == []

    # Approving/rejecting/cancelling are blocked too (defense in depth).
    assert (
        anon.post("/api/v1/requests/whatever/approve", headers=headers).status_code == 403
    )
    assert (
        anon.post("/api/v1/requests/whatever/reject", json={"reason": "x"}, headers=headers).status_code
        == 403
    )
    assert (
        anon.post("/api/v1/requests/whatever/cancel", headers=headers).status_code == 403
    )


def test_engineers_keep_self_service_and_directory(anon, session_factory):
    with session_factory() as session:
        _, project_id, _, eng_key = _seed(session)

    headers = {"x-api-key": eng_key}
    assert anon.get("/api/v1/departments", headers=headers).status_code == 200
    assert anon.get("/api/v1/teams", headers=headers).status_code == 200
    assert anon.get("/api/v1/requests", headers=headers).status_code == 200

    created = anon.post(
        "/api/v1/requests",
        json={
            "type": "membership",
            "payload": {"role": "client", "scope_type": "project", "scope_id": project_id},
        },
        headers=headers,
    )
    assert created.status_code == 200, created.text
    assert created.json()["status"] == "pending"


def test_client_plus_internal_role_can_still_request(anon, session_factory):
    """Union access: a user holding engineer + client keeps self-service."""
    with session_factory() as session:
        team_id, project_id, _, _ = _seed(session)
        from helpers import seed_user as _seed_user

        from aiobs_backend.models import Membership

        user, key = _seed_user(
            session, "both@x", role="client", scope_type="project", scope_id=project_id
        )
        session.add(
            Membership(
                user_id=user.id,
                role="engineer",
                scope_type="team",
                scope_id=team_id,
                status="approved",
            )
        )
        session.commit()

    headers = {"x-api-key": key}
    assert anon.get("/api/v1/requests", headers=headers).status_code == 200
    assert anon.get("/api/v1/teams", headers=headers).status_code == 200
