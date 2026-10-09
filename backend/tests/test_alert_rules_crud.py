"""Alert rule CRUD + scoped evaluation (audit item 7)."""
from __future__ import annotations

from datetime import datetime, timezone

from helpers import seed_department, seed_project, seed_team, seed_user

from aiobs_backend.alerts import evaluate_alerts
from aiobs_backend.models import AlertRule, Execution

_COUNTER = iter(range(20_000))


def _add_execution(
    session,
    project,
    *,
    started: datetime,
    status: str = "ok",
    total_tokens: int = 10,
    tool_calls: int = 1,
    duration_ms: float = 100,
    total_cost: float | None = None,
):
    session.add(
        Execution(
            trace_id=f"rule-{next(_COUNTER):05d}",
            project_id=project.id,
            workflow_name="wf",
            status=status,
            total_tokens=total_tokens,
            tool_calls=tool_calls,
            duration_ms=duration_ms,
            total_cost=total_cost,
            started_at=started,
            ended_at=started,
        )
    )


def _seed_org(session):
    department = seed_department(session, "Ops")
    team_a = seed_team(session, name="A", department=department)
    team_b = seed_team(session, name="B", department=department)
    p1 = seed_project(session, project_id="p1", api_key="k1", name="P1", team=team_a)
    p2 = seed_project(session, project_id="p2", api_key="k2", name="P2", team=team_b)
    return team_a, team_b, p1, p2


def test_builtin_rules_are_seeded(client):
    body = client.get("/api/v1/alert-rules").json()
    assert body["total"] == 5
    assert all(r["builtin"] for r in body["items"])
    assert {r["metric"] for r in body["items"]} == {
        "error_rate",
        "daily_tokens",
        "tool_calls_per_execution",
        "p95_latency",
        "cost_anomaly",
    }


def test_manager_rule_crud_matrix(anon, client, session_factory):
    with session_factory() as session:
        team_a, team_b, _, _ = _seed_org(session)
        _, mgr_key = seed_user(
            session, "mgr@x", role="manager", scope_type="team", scope_id=team_a.id
        )
        _, exec_key = seed_user(session, "exec@x", role="exec", scope_type="global")
        session.commit()
        team_a_id, team_b_id = team_a.id, team_b.id

    mgr = {"x-api-key": mgr_key}
    exec_headers = {"x-api-key": exec_key}

    # Manager sees the global builtins plus covered rules.
    listed = anon.get("/api/v1/alert-rules", headers=mgr).json()
    assert listed["total"] == 5 and all(r["scope_type"] == "global" for r in listed["items"])

    # Covered scope → OK.
    created = anon.post(
        "/api/v1/alert-rules",
        json={
            "name": "Team A errors",
            "metric": "error_rate",
            "warning_threshold": 0.3,
            "critical_threshold": 0.6,
            "scope_type": "team",
            "scope_id": team_a_id,
        },
        headers=mgr,
    )
    assert created.status_code == 200, created.text
    rule = created.json()
    assert rule["scope_name"] == "A"
    assert rule["builtin"] is False

    # Sibling team → 403; global → 403 for managers.
    denied = anon.post(
        "/api/v1/alert-rules",
        json={
            "name": "Sibling",
            "metric": "error_rate",
            "warning_threshold": 0.3,
            "critical_threshold": 0.6,
            "scope_type": "team",
            "scope_id": team_b_id,
        },
        headers=mgr,
    )
    assert denied.status_code == 403, denied.text
    assert (
        anon.post(
            "/api/v1/alert-rules",
            json={
                "name": "Global",
                "metric": "error_rate",
                "warning_threshold": 0.3,
                "critical_threshold": 0.6,
            },
            headers=mgr,
        ).status_code
        == 403
    )

    # Exec can create global rules; validation errors are clean.
    global_rule = anon.post(
        "/api/v1/alert-rules",
        json={
            "name": "Global errors",
            "metric": "error_rate",
            "warning_threshold": 0.3,
            "critical_threshold": 0.6,
        },
        headers=exec_headers,
    )
    assert global_rule.status_code == 200, global_rule.text
    assert (
        anon.post(
            "/api/v1/alert-rules",
            json={
                "name": "bad",
                "metric": "error_rate",
                "warning_threshold": 0.9,
                "critical_threshold": 0.1,
            },
            headers=exec_headers,
        ).status_code
        == 422
    )
    assert (
        anon.post(
            "/api/v1/alert-rules",
            json={
                "name": "bad metric",
                "metric": "nope",
                "warning_threshold": 0.1,
                "critical_threshold": 0.2,
            },
            headers=exec_headers,
        ).status_code
        == 422
    )
    assert (
        anon.post(
            "/api/v1/alert-rules",
            json={
                "name": "bad scope",
                "metric": "error_rate",
                "warning_threshold": 0.1,
                "critical_threshold": 0.2,
                "scope_type": "team",
                "scope_id": "no-such-team",
            },
            headers=exec_headers,
        ).status_code
        == 404
    )

    # Manager patches their rule; cannot touch builtins.
    patched = anon.patch(
        f"/api/v1/alert-rules/{rule['id']}",
        json={"warning_threshold": 0.25, "enabled": False},
        headers=mgr,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["warning_threshold"] == 0.25
    assert patched.json()["enabled"] is False
    builtin = next(
        r for r in client.get("/api/v1/alert-rules").json()["items"] if r["builtin"]
    )
    assert (
        anon.patch(
            f"/api/v1/alert-rules/{builtin['id']}", json={"enabled": False}, headers=mgr
        ).status_code
        == 403
    )

    # Builtins cannot be deleted; admin disables instead.
    assert client.delete(f"/api/v1/alert-rules/{builtin['id']}").status_code == 409
    assert (
        client.patch(
            f"/api/v1/alert-rules/{builtin['id']}", json={"enabled": False}
        ).status_code
        == 200
    )

    # Manager deletes their own rule; sibling rule delete is 403.
    assert anon.delete(f"/api/v1/alert-rules/{rule['id']}", headers=mgr).status_code == 200
    assert (
        anon.delete(
            f"/api/v1/alert-rules/{global_rule.json()['id']}", headers=mgr
        ).status_code
        == 403
    )
    assert (
        client.delete(f"/api/v1/alert-rules/{global_rule.json()['id']}").status_code
        == 200
    )


def test_scoped_rule_evaluation_and_dedupe(client, session_factory):
    with session_factory() as session:
        team_a, _, p1, p2 = _seed_org(session)
        # Isolate the custom rule: global builtins would alert on the same data.
        for rule in session.query(AlertRule).filter_by(builtin=True).all():
            rule.enabled = False
        session.add(
            AlertRule(
                name="Team A error rate",
                metric="error_rate",
                warning_threshold=0.4,
                critical_threshold=0.9,
                scope_type="team",
                scope_id=team_a.id,
            )
        )
        session.commit()
        p1_id, p2_id = p1.id, p2.id

    now = datetime.now(timezone.utc)
    # Failures in the *other* team do not count for a team-A rule.
    with session_factory() as session:
        from aiobs_backend.models import Project

        other = session.get(Project, p2_id)
        for i in range(6):
            _add_execution(session, other, started=now, status="error")
        session.commit()
        created = evaluate_alerts(session)
        session.commit()
    assert not [
        a for a in created if a["dimension"] == "rule" and a["dimension_key"] == "error_rate"
    ], created

    # Failures inside team A's project trigger warning + critical once.
    with session_factory() as session:
        from aiobs_backend.models import Project

        mine = session.get(Project, p1_id)
        for i in range(6):
            _add_execution(session, mine, started=now, status="error")
        session.commit()
        created = evaluate_alerts(session)
        session.commit()
    scoped = [a for a in created if a["dimension_key"] == "error_rate"]
    assert scoped, created
    assert {a["severity"] for a in scoped} == {"warning", "critical"}
    assert all(a["rule_ref"] for a in scoped)

    with session_factory() as session:
        again = evaluate_alerts(session)
    assert not [a for a in again if a["dimension_key"] == "error_rate"], again


def test_disabled_rule_stops_alerts(session_factory, project):
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        for rule in session.query(AlertRule).filter_by(metric="error_rate").all():
            rule.enabled = False
        for i in range(6):
            _add_execution(session, project, started=now, status="error")
        session.commit()
        created = evaluate_alerts(session)
        session.commit()
    assert not [a for a in created if a["dimension"] == "rule"], created
