"""Scoped alert acknowledgment + rule alert visibility (audit item 7, #08)."""
from __future__ import annotations

from datetime import datetime, timezone

from helpers import seed_department, seed_project, seed_team, seed_user

from aiobs_backend.models import Alert, AlertRule, Budget

KEY = "test-key"


def _seed_org(session):
    department = seed_department(session, "Ops")
    team_a = seed_team(session, name="A", department=department)
    team_b = seed_team(session, name="B", department=department)
    p1 = seed_project(session, project_id="p1", api_key="k1", name="P1", team=team_a)
    p2 = seed_project(session, project_id="p2", api_key="k2", name="P2", team=team_b)
    now = datetime.now(timezone.utc)
    budget_a = Budget(amount=10, period=now, name="cap A", project_id=p1.id)
    budget_b = Budget(amount=10, period=now, name="cap B", project_id=p2.id)
    rule_team = AlertRule(
        name="team A errors",
        metric="error_rate",
        warning_threshold=0.4,
        critical_threshold=0.9,
        scope_type="team",
        scope_id=team_a.id,
    )
    rule_global = AlertRule(
        name="global errors",
        metric="error_rate",
        warning_threshold=0.4,
        critical_threshold=0.9,
        scope_type="global",
    )
    session.add_all([budget_a, budget_b, rule_team, rule_global])
    session.flush()
    alerts = {
        "budget_a": Alert(
            rule_id="budget:a",
            severity="warning",
            message="Budget approaching: cap A",
            dimension="budget",
            dimension_key=budget_a.id,
        ),
        "budget_b": Alert(
            rule_id="budget:b",
            severity="warning",
            message="Budget approaching: cap B",
            dimension="budget",
            dimension_key=budget_b.id,
        ),
        "rule_team_a": Alert(
            rule_id="rule:team-a",
            severity="warning",
            message="team A errors high",
            dimension="rule",
            dimension_key="error_rate",
            rule_ref=rule_team.id,
        ),
        "rule_global": Alert(
            rule_id="rule:global",
            severity="warning",
            message="global errors high",
            dimension="rule",
            dimension_key="error_rate",
            rule_ref=rule_global.id,
        ),
    }
    session.add_all(alerts.values())
    session.commit()
    return {
        "team_a": team_a.id,
        "p1": p1.id,
        **{k: v.id for k, v in alerts.items()},
    }


def test_manager_ack_scope(anon, client, session_factory):
    with session_factory() as session:
        ids = _seed_org(session)
        _, mgr_key = seed_user(
            session, "mgr@x", role="manager", scope_type="team", scope_id=ids["team_a"]
        )
        _, exec_key = seed_user(session, "exec@x", role="exec", scope_type="global")
        session.commit()

    mgr = {"x-api-key": mgr_key}

    listed = anon.get("/api/v1/alerts", headers=mgr).json()
    visible = {a["id"]: a for a in listed["items"]}
    assert ids["budget_a"] in visible
    assert ids["rule_team_a"] in visible
    assert ids["budget_b"] not in visible
    assert ids["rule_global"] not in visible
    assert visible[ids["budget_a"]]["can_ack"] is True
    assert visible[ids["rule_team_a"]]["can_ack"] is True
    assert visible[ids["budget_a"]]["scope"] == "project"

    # Ack in scope works; out of scope is 403.
    assert (
        anon.patch(
            f"/api/v1/alerts/{ids['budget_a']}", params={"status": "acknowledged"}, headers=mgr
        ).status_code
        == 200
    )
    assert (
        anon.patch(
            f"/api/v1/alerts/{ids['budget_b']}", params={"status": "acknowledged"}, headers=mgr
        ).status_code
        == 403
    )
    assert (
        anon.patch(
            f"/api/v1/alerts/{ids['rule_global']}", params={"status": "acknowledged"}, headers=mgr
        ).status_code
        == 403
    )
    # Invalid status / unknown id.
    assert (
        anon.patch(
            f"/api/v1/alerts/{ids['budget_a']}", params={"status": "sideways"}, headers=mgr
        ).status_code
        == 400
    )
    assert (
        anon.patch("/api/v1/alerts/nope", params={"status": "closed"}, headers=mgr).status_code
        == 404
    )

    # Exec sees and closes the global rule alert.
    exec_headers = {"x-api-key": exec_key}
    exec_list = anon.get("/api/v1/alerts", headers=exec_headers).json()
    assert exec_list["total"] == 4
    assert (
        anon.patch(
            f"/api/v1/alerts/{ids['rule_global']}",
            params={"status": "closed"},
            headers=exec_headers,
        ).status_code
        == 200
    )

    # Admin key can ack anything.
    assert (
        client.patch(
            f"/api/v1/alerts/{ids['budget_b']}", params={"status": "closed"}
        ).status_code
        == 200
    )


def test_client_sees_alert_but_cannot_ack(anon, session_factory):
    with session_factory() as session:
        ids = _seed_org(session)
        # Client membership needs the internal project id; look it up.
        from aiobs_backend.models import Project

        p1 = session.get(Project, ids["p1"])
        _, client_key = seed_user(
            session, "cli@x", role="client", scope_type="project", scope_id=p1.id
        )
        session.commit()

    headers = {"x-api-key": client_key}
    listed = anon.get("/api/v1/alerts", headers=headers).json()
    visible = {a["id"]: a for a in listed["items"]}
    assert ids["budget_a"] in visible  # their project's budget alert
    assert ids["budget_b"] not in visible
    assert ids["rule_global"] not in visible
    assert all(a["can_ack"] is False for a in visible.values())
    assert (
        anon.patch(
            f"/api/v1/alerts/{ids['budget_a']}", params={"status": "closed"}, headers=headers
        ).status_code
        == 403
    )
