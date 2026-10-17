"""Project rates (margin 02): versioned revenue/manual-cost inputs (ADR-0013)."""
from __future__ import annotations

from helpers import seed_user


def _exec_key(session, email: str = "exec@x") -> str:
    _, key = seed_user(session, email, role="exec", scope_type="global")
    session.commit()
    return key


def _headers(key: str) -> dict:
    return {"x-api-key": key}


def test_exec_maintains_rate_versions(anon, session_factory, project):
    with session_factory() as session:
        key = _exec_key(session)

    created = anon.post(
        "/api/v1/project-rates",
        json={
            "project_id": "proj-1",
            "effective_from": "2026-10-01",
            "revenue_amount": 300,
            "revenue_period": "month",
            "manual_cost_amount": 50,
            "manual_cost_period": "month",
        },
        headers=_headers(key),
    )
    assert created.status_code == 200, created.text
    rate = created.json()
    assert rate["project_id"] == "proj-1"
    assert rate["project_name"] == "Test Project"
    assert rate["revenue_amount"] == 300
    assert rate["manual_cost_amount"] == 50
    assert rate["effective_from"] == "2026-10-01"

    # A second version on a later date coexists — versions never overwrite.
    second = anon.post(
        "/api/v1/project-rates",
        json={
            "project_id": "proj-1",
            "effective_from": "2026-11-01",
            "revenue_amount": 400,
        },
        headers=_headers(key),
    )
    assert second.status_code == 200, second.text

    listed = anon.get("/api/v1/project-rates", headers=_headers(key)).json()
    assert listed["total"] == 1  # one project, two versions
    entry = listed["items"][0]
    assert entry["project_id"] == "proj-1"
    assert entry["project_name"] == "Test Project"
    assert entry["internal"] is False
    assert [version["effective_from"] for version in entry["versions"]] == [
        "2026-11-01",
        "2026-10-01",
    ]


def test_duplicate_effective_from_is_a_conflict(anon, session_factory, project):
    with session_factory() as session:
        key = _exec_key(session)

    body = {
        "project_id": "proj-1",
        "effective_from": "2026-10-01",
        "revenue_amount": 300,
    }
    assert anon.post("/api/v1/project-rates", json=body, headers=_headers(key)).status_code == 200
    clash = anon.post("/api/v1/project-rates", json=body, headers=_headers(key))
    assert clash.status_code == 409
    assert "already starts on" in clash.json()["detail"]

    # Nothing was overwritten: one version, unchanged.
    listed = anon.get("/api/v1/project-rates", headers=_headers(key)).json()
    assert len(listed["items"][0]["versions"]) == 1


def test_versions_are_editable_and_deletable(anon, session_factory, project):
    with session_factory() as session:
        key = _exec_key(session)

    first = anon.post(
        "/api/v1/project-rates",
        json={"project_id": "proj-1", "effective_from": "2026-10-01", "revenue_amount": 300},
        headers=_headers(key),
    ).json()
    second = anon.post(
        "/api/v1/project-rates",
        json={"project_id": "proj-1", "effective_from": "2026-11-01", "revenue_amount": 400},
        headers=_headers(key),
    ).json()

    edited = anon.patch(
        f"/api/v1/project-rates/{first['id']}",
        json={"revenue_amount": 350, "manual_cost_amount": 25, "revenue_period": "year"},
        headers=_headers(key),
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["revenue_amount"] == 350
    assert edited.json()["manual_cost_amount"] == 25
    assert edited.json()["revenue_period"] == "year"

    # Editing into another version's date is refused, not silently merged.
    clash = anon.patch(
        f"/api/v1/project-rates/{first['id']}",
        json={"effective_from": "2026-11-01"},
        headers=_headers(key),
    )
    assert clash.status_code == 409

    removed = anon.delete(f"/api/v1/project-rates/{second['id']}", headers=_headers(key))
    assert removed.status_code == 200
    listed = anon.get("/api/v1/project-rates", headers=_headers(key)).json()
    assert [version["id"] for version in listed["items"][0]["versions"]] == [first["id"]]


def test_rate_writes_are_exec_only(anon, session_factory, project):
    with session_factory() as session:
        _, manager_key = seed_user(
            session,
            "mgr@x",
            role="manager",
            scope_type="team",
            scope_id=project.team_id,
        )
        _, client_key = seed_user(
            session, "cli@x", role="client", scope_type="project", scope_id=project.id
        )
        session.commit()

    body = {
        "project_id": "proj-1",
        "effective_from": "2026-10-01",
        "revenue_amount": 300,
    }
    assert anon.post("/api/v1/project-rates", json=body, headers=_headers(manager_key)).status_code == 403
    assert anon.post("/api/v1/project-rates", json=body, headers=_headers(client_key)).status_code == 403
    assert anon.get("/api/v1/project-rates", headers=_headers(manager_key)).status_code == 403
    assert anon.get("/api/v1/project-rates", headers=_headers(client_key)).status_code == 403


def test_rate_validation_and_unknown_project(anon, session_factory, project):
    with session_factory() as session:
        key = _exec_key(session)

    unknown = anon.post(
        "/api/v1/project-rates",
        json={"project_id": "nope", "effective_from": "2026-10-01", "revenue_amount": 10},
        headers=_headers(key),
    )
    assert unknown.status_code == 404

    negative = anon.post(
        "/api/v1/project-rates",
        json={"project_id": "proj-1", "effective_from": "2026-10-01", "revenue_amount": -1},
        headers=_headers(key),
    )
    assert negative.status_code == 422

    bad_period = anon.post(
        "/api/v1/project-rates",
        json={
            "project_id": "proj-1",
            "effective_from": "2026-10-01",
            "revenue_amount": 10,
            "revenue_period": "week",
        },
        headers=_headers(key),
    )
    assert bad_period.status_code == 422

    missing = anon.patch(
        "/api/v1/project-rates/nope", json={"revenue_amount": 1}, headers=_headers(key)
    )
    assert missing.status_code == 404


def test_internal_flag_is_exec_maintained(anon, session_factory, project):
    with session_factory() as session:
        key = _exec_key(session)
        _, manager_key = seed_user(
            session,
            "mgr@internal",
            role="manager",
            scope_type="team",
            scope_id=project.team_id,
        )
        session.commit()

    flagged = anon.patch(
        "/api/v1/project-rates/proj-1/internal",
        json={"internal": True},
        headers=_headers(key),
    )
    assert flagged.status_code == 200, flagged.text
    assert flagged.json()["internal"] is True

    entry = anon.get("/api/v1/project-rates", headers=_headers(key)).json()["items"][0]
    assert entry["project_id"] == "proj-1"
    assert entry["internal"] is True
    assert entry["versions"] == []

    # Managers cannot flip it, and unknown projects are 404.
    assert (
        anon.patch(
            "/api/v1/project-rates/proj-1/internal",
            json={"internal": False},
            headers=_headers(manager_key),
        ).status_code
        == 403
    )
    assert (
        anon.patch(
            "/api/v1/project-rates/nope/internal",
            json={"internal": True},
            headers=_headers(key),
        ).status_code
        == 404
    )
