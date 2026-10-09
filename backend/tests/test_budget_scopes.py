"""Budget department/team scopes and scoped manager CRUD (audit item 5)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from helpers import (
    build_request,
    build_span,
    seed_department,
    seed_project,
    seed_team,
    seed_user,
)

KEY = "test-key"


def _headers(project: str = "p1", key: str = KEY):
    return {"x-project-name": project, "authorization": f"Bearer {key}"}


def _trace(trace_id: int, project: str = "p1"):
    now = datetime.now(timezone.utc)
    root = build_span(
        name="checkout",
        oi_kind="CHAIN",
        span_id=1,
        trace_id=trace_id,
        start=now,
        end=now + timedelta(seconds=1),
        attrs={"sdk.project_id": project, "sdk.client_id": "client-42"},
    )
    llm = build_span(
        name="llm_call",
        oi_kind="LLM",
        span_id=2,
        trace_id=trace_id,
        parent_span_id=1,
        start=now + timedelta(milliseconds=100),
        end=now + timedelta(seconds=1),
        attrs={
            "llm.model_name": "gpt-4o-mini",
            "llm.provider": "openai",
            "llm.token_count.prompt": 1000,
            "llm.token_count.completion": 500,
        },
    )
    return [root, llm]


def _ingest(client, trace_id: int, project: str = "p1", key: str = KEY) -> None:
    resp = client.post(
        "/api/v1/traces",
        content=build_request(_trace(trace_id, project)),
        headers=_headers(project, key),
    )
    assert resp.status_code == 200, resp.text


def _seed_two_units(session):
    """Department D (team A → p1) and department D2 (team B → p2)."""
    d = seed_department(session, "D")
    team_a = seed_team(session, name="A", department=d)
    p1 = seed_project(session, project_id="p1", api_key=KEY, name="P1", team=team_a)
    d2 = seed_department(session, "D2")
    team_b = seed_team(session, name="B", department=d2)
    p2 = seed_project(session, project_id="p2", api_key="k2", name="P2", team=team_b)
    return d, team_a, p1, d2, team_b, p2


def test_department_budget_counts_only_its_unit(anon, client, session_factory):
    with session_factory() as session:
        d, team_a, _, _, _, _ = _seed_two_units(session)
        session.commit()
        department_id = d.id

    _ingest(anon, 3201, project="p1", key=KEY)
    _ingest(anon, 3202, project="p2", key="k2")

    created = client.post(
        "/api/v1/budgets",
        json={
            "name": "dept cap",
            "amount": 1.0,
            "period": "2000-01-01",
            "period_type": "month",
            "department": department_id,
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["scope"] == "department"

    item = client.get("/api/v1/budgets/status").json()["items"][0]
    # Only p1 (team A, dept D) counts — 0.00045, not the double from p2.
    assert abs(item["spend"] - 0.00045) < 1e-9, item


def test_team_budget_counts_only_that_team(anon, client, session_factory):
    with session_factory() as session:
        _, team_a, _, _, _, _ = _seed_two_units(session)
        session.commit()
        team_a_id = team_a.id

    _ingest(anon, 3211, project="p1", key=KEY)
    _ingest(anon, 3212, project="p2", key="k2")
    client.post(
        "/api/v1/budgets",
        json={
            "name": "team cap",
            "amount": 1.0,
            "period": "2000-01-01",
            "team": team_a_id,
        },
    )
    item = client.get("/api/v1/budgets/status").json()["items"][0]
    assert abs(item["spend"] - 0.00045) < 1e-9, item


def test_manager_scoped_create_matrix(anon, client, session_factory):
    with session_factory() as session:
        _, team_a, _, _, team_b, _ = _seed_two_units(session)
        _, mgr_key = seed_user(
            session, "mgr@x", role="manager", scope_type="team", scope_id=team_a.id
        )
        _, exec_key = seed_user(session, "exec@x", role="exec", scope_type="global")
        session.commit()
        team_a_id, team_b_id = team_a.id, team_b.id

    mgr = {"x-api-key": mgr_key}
    # Covered team scope → OK.
    ok = anon.post(
        "/api/v1/budgets",
        json={"amount": 5, "period": "2026-09-01", "team": team_a_id},
        headers=mgr,
    )
    assert ok.status_code == 200, ok.text

    # Covered via the team's project → OK.
    ok_project = anon.post(
        "/api/v1/budgets",
        json={"amount": 5, "period": "2026-09-01", "project": "p1"},
        headers=mgr,
    )
    assert ok_project.status_code == 200, ok_project.text

    # Sibling team → 403.
    denied = anon.post(
        "/api/v1/budgets",
        json={"amount": 5, "period": "2026-09-01", "team": team_b_id},
        headers=mgr,
    )
    assert denied.status_code == 403, denied.text

    # Unscoped → 403 for managers.
    unscoped = anon.post(
        "/api/v1/budgets",
        json={"amount": 5, "period": "2026-09-01"},
        headers=mgr,
    )
    assert unscoped.status_code == 403, unscoped.text

    # Unscoped is fine for exec.
    exec_ok = anon.post(
        "/api/v1/budgets",
        json={"amount": 5, "period": "2026-09-01"},
        headers={"x-api-key": exec_key},
    )
    assert exec_ok.status_code == 200, exec_ok.text


def test_manager_budget_visibility_and_manage(anon, client, session_factory):
    with session_factory() as session:
        _, team_a, _, _, team_b, p2 = _seed_two_units(session)
        _, mgr_key = seed_user(
            session, "mgr2@x", role="manager", scope_type="team", scope_id=team_a.id
        )
        session.commit()
        team_a_id, team_b_id = team_a.id, team_b.id

    admin = {"x-admin-key": "admin"}
    covered = client.post(
        "/api/v1/budgets",
        json={"name": "covered", "amount": 10, "period": "2026-09-01", "team": team_a_id},
        headers=admin,
    ).json()
    other = client.post(
        "/api/v1/budgets",
        json={"name": "other", "amount": 10, "period": "2026-09-01", "team": team_b_id},
        headers=admin,
    ).json()
    global_budget = client.post(
        "/api/v1/budgets",
        json={"name": "global", "amount": 10, "period": "2026-09-01"},
        headers=admin,
    ).json()

    mgr = {"x-api-key": mgr_key}
    listed = anon.get("/api/v1/budgets", headers=mgr).json()
    assert [b["name"] for b in listed["items"]] == ["covered"]

    status = anon.get("/api/v1/budgets/status", headers=mgr).json()
    assert [b["name"] for b in status["items"]] == ["covered"]

    assert client.get("/api/v1/budgets").json()["total"] == 3

    # PATCH the covered budget.
    patched = anon.patch(
        f"/api/v1/budgets/{covered['id']}",
        json={"amount": 20, "name": "renamed"},
        headers=mgr,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["amount"] == 20
    assert patched.json()["name"] == "renamed"

    # PATCH/delete out-of-scope → 403.
    assert (
        anon.patch(
            f"/api/v1/budgets/{other['id']}", json={"amount": 1}, headers=mgr
        ).status_code
        == 403
    )
    assert anon.delete(f"/api/v1/budgets/{global_budget['id']}").status_code == 401
    assert anon.delete(f"/api/v1/budgets/{other['id']}", headers=mgr).status_code == 403

    # Deleting the covered budget works for the manager.
    assert anon.delete(f"/api/v1/budgets/{covered['id']}", headers=mgr).status_code == 200
    assert client.get("/api/v1/budgets").json()["total"] == 2

    # Unknown scope ids are 400, not 500.
    bad = anon.post(
        "/api/v1/budgets",
        json={"amount": 1, "period": "2026-09-01", "team": "no-such-team"},
        headers=mgr,
    )
    assert bad.status_code == 400, bad.text
