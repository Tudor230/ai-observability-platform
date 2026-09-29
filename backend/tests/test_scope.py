"""Membership-derived scoping and client cost stripping (ADR-0006)."""
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

from aiobs_backend.models import Membership

KEY = "test-key"
CSRF = {"x-requested-with": "aiobs"}


def _trace(trace_id: int, project_id: str):
    now = datetime.now(timezone.utc)
    root = build_span(
        name="checkout",
        oi_kind="CHAIN",
        span_id=1,
        trace_id=trace_id,
        start=now,
        end=now + timedelta(seconds=2),
        attrs={"sdk.project_id": project_id, "sdk.client_id": "client-42"},
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
            "llm.token_count.total": 1500,
        },
    )
    return [root, llm]


def _seed_org(session):
    department = seed_department(session, "Ops")
    team_a = seed_team(session, name="A", department=department)
    team_b = seed_team(session, name="B", department=department)
    p1 = seed_project(session, project_id="p1", api_key=KEY, name="P1", team=team_a)
    p2 = seed_project(session, project_id="p2", api_key="k2", name="P2", team=team_b)
    return department, team_a, team_b, p1, p2


def _ingest(anon, project: str, key: str, trace_id: int) -> None:
    resp = anon.post(
        "/api/v1/traces",
        content=build_request(_trace(trace_id, project)),
        headers={"x-project-name": project, "authorization": f"Bearer {key}"},
    )
    assert resp.status_code == 200, resp.text


def test_team_membership_scopes_lists_and_404s(anon, session_factory):
    with session_factory() as session:
        _, team_a, _, p1, p2 = _seed_org(session)
        user, key = seed_user(
            session, "eng@x", role="engineer", scope_type="team", scope_id=team_a.id
        )
        session.commit()
        user_id, p2_id = user.id, p2.id

    _ingest(anon, "p1", KEY, 2101)
    _ingest(anon, "p2", "k2", 2102)
    headers = {"x-api-key": key}

    items = anon.get("/api/v1/executions", headers=headers).json()["items"]
    assert [i["project_id"] for i in items] == ["p1"]
    # Requesting an out-of-scope project is a 404, not a silent empty list.
    assert anon.get("/api/v1/executions?project_id=p2", headers=headers).status_code == 404
    assert (
        anon.get(
            "/api/v1/executions", headers={**headers, "x-project-name": "p2"}
        ).status_code
        == 404
    )

    # A second membership (client on p2) unions the visible projects.
    with session_factory() as session:
        session.add(
            Membership(
                user_id=user_id,
                role="client",
                scope_type="project",
                scope_id=p2_id,
                status="approved",
            )
        )
        session.commit()
    items = anon.get("/api/v1/executions", headers=headers).json()["items"]
    assert {i["project_id"] for i in items} == {"p1", "p2"}


def test_client_costs_are_stripped(anon, session_factory):
    with session_factory() as session:
        _, team_a, _, p1, _ = _seed_org(session)
        user, key = seed_user(
            session, "cli@x", role="client", scope_type="project", scope_id=p1.id
        )
        _, eng_key = seed_user(
            session, "eng2@x", role="engineer", scope_type="team", scope_id=team_a.id
        )
        session.commit()

    _ingest(anon, "p1", KEY, 2111)
    client_headers = {"x-api-key": key}

    item = anon.get("/api/v1/executions", headers=client_headers).json()["items"][0]
    assert "total_cost" not in item
    assert "cost_complete" not in item
    detail = anon.get(
        f"/api/v1/executions/{item['id']}", headers=client_headers
    ).json()
    assert "total_cost" not in detail
    workflows = anon.get("/api/v1/workflows", headers=client_headers).json()["items"]
    assert workflows and all("total_cost" not in w for w in workflows)
    overview = anon.get("/api/v1/overview", headers=client_headers).json()
    assert "total_cost" not in overview
    assert "total_cost_pct" not in overview["deltas"]
    spans = anon.get(
        f"/api/v1/executions/{item['id']}/spans", headers=client_headers
    ).json()["items"]
    assert spans and all("cost" not in s and "attributes" not in s for s in spans)

    # The same project's engineer still sees costs.
    eng_item = anon.get(
        "/api/v1/executions", headers={"x-api-key": eng_key}
    ).json()["items"][0]
    assert eng_item["total_cost"] is not None


def test_exec_sees_business_not_trace_detail(anon, session_factory):
    with session_factory() as session:
        _seed_org(session)
        _, key = seed_user(session, "exec@x", role="exec", scope_type="global")
        session.commit()
    headers = {"x-api-key": key}
    assert anon.get("/api/v1/costs", headers=headers).status_code == 200
    assert anon.get("/api/v1/workflows", headers=headers).status_code == 200
    assert anon.get("/api/v1/executions", headers=headers).status_code == 403


def test_manager_budgets_are_scoped(anon, client, session_factory):
    with session_factory() as session:
        _, team_a, _, _, p2 = _seed_org(session)
        _, key = seed_user(
            session, "mgr@x", role="manager", scope_type="team", scope_id=team_a.id
        )
        session.commit()

    created = client.post(
        "/api/v1/budgets",
        json={"amount": 100, "period": "2026-09-01", "project": "p2"},
    )
    assert created.status_code == 200, created.text

    scoped = anon.get("/api/v1/budgets/status", headers={"x-api-key": key}).json()
    assert scoped["total"] == 0
    assert client.get("/api/v1/budgets/status").json()["total"] == 1
