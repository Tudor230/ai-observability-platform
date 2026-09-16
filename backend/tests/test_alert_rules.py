"""Threshold alert rules (F04): non-budget consumption/quality alerts."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiobs_backend.alerts import evaluate_alerts
from aiobs_backend.models import Execution

_COUNTER = iter(range(10_000))


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
            trace_id=f"alert-{next(_COUNTER):05d}",
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


def test_error_rate_rule_fires_once_per_day(session_factory, project):
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        for i in range(6):
            _add_execution(
                session, project, started=now, status="error" if i < 4 else "ok"
            )
        session.commit()
        created = evaluate_alerts(session)
        session.commit()
    rules = {a["rule_id"] for a in created}
    assert any(r.startswith("rule:error_rate:") for r in rules), rules
    assert all(a["dimension"] == "rule" for a in created if a["rule_id"].startswith("rule:error_rate"))

    with session_factory() as session:
        again = evaluate_alerts(session)
    assert not any(a["rule_id"].startswith("rule:error_rate") for a in again)


def test_token_tool_and_latency_rules(session_factory, project):
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        for _ in range(5):
            _add_execution(
                session,
                project,
                started=now,
                total_tokens=500_000,  # 2.5M total > 2M threshold
                tool_calls=30,  # 30/execution > 20 threshold
                duration_ms=60_000,  # p95 60s > 30s threshold
            )
        session.commit()
        created = evaluate_alerts(session)
        session.commit()
    keys = {a["dimension_key"] for a in created}
    assert {"tokens", "tool_calls", "latency_p95"} <= keys, keys


def test_rules_need_a_minimum_sample(session_factory, project):
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        for _ in range(2):  # below AIOBS_ALERT_MIN_EXECUTIONS
            _add_execution(session, project, started=now, status="error")
        session.commit()
        created = evaluate_alerts(session)
    assert not [a for a in created if a["dimension"] == "rule"], created


def test_cost_anomaly_rule(session_factory, project):
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        # 7-day baseline: 0.01/day in total.
        for day in range(1, 8):
            _add_execution(
                session, project, started=now - timedelta(days=day), total_cost=0.01
            )
        # Today: 5 executions at 0.2 each = 1.0 (~14x the daily average).
        for _ in range(5):
            _add_execution(session, project, started=now, total_cost=0.2)
        session.commit()
        created = evaluate_alerts(session)
        session.commit()
    keys = {a["dimension_key"] for a in created}
    assert "cost_anomaly" in keys, created


def test_rule_alerts_do_not_trigger_budget_alerts(session_factory, project):
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        for _ in range(5):
            _add_execution(session, project, started=now)
        session.commit()
        created = evaluate_alerts(session)
        session.commit()
    assert not [a for a in created if a["dimension"] == "rule"], created


def test_alerts_are_posted_to_the_webhook(monkeypatch, session_factory, project):
    """F37: created alerts are delivered best-effort to the configured webhook."""
    import json as jsonlib

    from aiobs_backend import alerts as alerts_mod
    from aiobs_backend.config import get_settings

    sent: dict = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(request, timeout=None):
        sent["url"] = request.full_url
        sent["payload"] = jsonlib.loads(request.data.decode("utf-8"))
        return _Response()

    get_settings.cache_clear()
    monkeypatch.setattr(alerts_mod.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        get_settings(), "alert_webhook_url", "http://hooks.test/alerts"
    )
    try:
        now = datetime.now(timezone.utc)
        with session_factory() as session:
            for i in range(6):
                _add_execution(
                    session, project, started=now, status="error" if i < 5 else "ok"
                )
            session.commit()
            created = evaluate_alerts(session)
            session.commit()
        assert created, "expected the error-rate alert"
        assert sent["url"] == "http://hooks.test/alerts"
        assert sent["payload"]["alerts"]
        assert sent["payload"]["alerts"][0]["rule_id"].startswith("rule:error_rate")
    finally:
        get_settings.cache_clear()
