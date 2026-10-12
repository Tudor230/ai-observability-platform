"""Failures-by-kind series + budget burn-down series (refinements v2)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from helpers import seed_department, seed_project, seed_team, seed_user

from aiobs_backend.models import Execution


def _execution(
    session,
    project,
    *,
    trace: str,
    started: datetime,
    kind: str | None = None,
    cost: float | None = None,
) -> None:
    session.add(
        Execution(
            trace_id=trace,
            project_id=project.id,
            workflow_name="wf",
            status="error" if kind else "ok",
            root_error_kind=kind,
            total_cost=cost,
            total_tokens=10,
            started_at=started,
            ended_at=started,
        )
    )


def test_failures_series_grouping_and_scope(anon, session_factory):
    with session_factory() as session:
        department = seed_department(session, "Ops")
        team_a = seed_team(session, name="A", department=department)
        team_b = seed_team(session, name="B", department=department)
        p1 = seed_project(session, project_id="p1", api_key="k1", name="P1", team=team_a)
        p2 = seed_project(session, project_id="p2", api_key="k2", name="P2", team=team_b)
        _, eng_key = seed_user(
            session, "eng-s@x", role="engineer", scope_type="team", scope_id=team_a.id
        )
        now = datetime.now(timezone.utc)
        _execution(session, p1, trace="t1", started=now - timedelta(days=1), kind="rate_limit")
        _execution(session, p1, trace="t2", started=now - timedelta(days=1), kind="tool_error")
        _execution(session, p2, trace="t3", started=now - timedelta(days=1), kind="timeout")
        _execution(session, p1, trace="t4", started=now)  # ok execution: excluded
        session.commit()

    admin = anon.get(
        "/api/v1/failures/series",
        params={"days": 7},
        headers={"x-admin-key": "admin"},
    ).json()
    assert set(admin["kinds"]) == {"rate_limit", "tool_error", "timeout"}
    assert sum(item["count"] for item in admin["items"]) == 3
    assert all(item["kind"] != "ok" for item in admin["items"])

    scoped = anon.get(
        "/api/v1/failures/series", params={"days": 7}, headers={"x-api-key": eng_key}
    ).json()
    assert set(scoped["kinds"]) == {"rate_limit", "tool_error"}
    assert sum(item["count"] for item in scoped["items"]) == 2


def test_budget_series_cumulative_and_visibility(anon, client, session_factory):
    with session_factory() as session:
        department = seed_department(session, "Ops")
        team_a = seed_team(session, name="A", department=department)
        team_b = seed_team(session, name="B", department=department)
        p1 = seed_project(session, project_id="p1s", api_key="k", name="P1", team=team_a)
        _, mgr_key = seed_user(
            session, "mgr-s@x", role="manager", scope_type="team", scope_id=team_a.id
        )
        _, sibling_key = seed_user(
            session, "mgr-b@x", role="manager", scope_type="team", scope_id=team_b.id
        )
        _, client_key = seed_user(
            session, "cli-s@x", role="client", scope_type="project", scope_id=p1.id
        )
        now = datetime.now(timezone.utc)
        _execution(session, p1, trace="b1", started=now - timedelta(hours=2), cost=0.5)
        session.commit()

    created = client.post(
        "/api/v1/budgets",
        json={"amount": 10, "period": "2020-01-01", "period_type": "month", "project": "p1s"},
    ).json()

    series = anon.get(
        f"/api/v1/budgets/{created['id']}/series", headers={"x-api-key": mgr_key}
    ).json()
    assert series["amount"] == 10
    assert series["items"], series
    assert abs(series["items"][-1]["cumulative"] - 0.5) < 1e-9
    assert series["period_start"] < series["period_end"]

    # Sibling manager: hidden (404); client: role gate (403).
    assert (
        anon.get(
            f"/api/v1/budgets/{created['id']}/series", headers={"x-api-key": sibling_key}
        ).status_code
        == 404
    )
    assert (
        anon.get(
            f"/api/v1/budgets/{created['id']}/series", headers={"x-api-key": client_key}
        ).status_code
        == 403
    )
