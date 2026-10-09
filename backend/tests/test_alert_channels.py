"""Alert channels: CRUD, rule routing, email/Slack/webhook delivery (#07)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from helpers import seed_user

from aiobs_backend import notify
from aiobs_backend.alerts import evaluate_alerts
from aiobs_backend.config import get_settings
from aiobs_backend.models import AlertChannel, AlertRule, Execution, alert_rule_channels

_COUNTER = iter(range(30_000))


def _add_execution(session, project, *, started, status="error", total_tokens=10):
    session.add(
        Execution(
            trace_id=f"chan-{next(_COUNTER):05d}",
            project_id=project.id,
            workflow_name="wf",
            status=status,
            total_tokens=total_tokens,
            tool_calls=1,
            duration_ms=100,
            started_at=started,
            ended_at=started,
        )
    )


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _capture_urlopen(monkeypatch, sent):
    def fake_urlopen(request, timeout=None):
        sent.append(
            {"url": request.full_url, "payload": json.loads(request.data.decode("utf-8"))}
        )
        return _Response()

    monkeypatch.setattr(notify.urllib.request, "urlopen", fake_urlopen)


class _FakeSMTP:
    instances: list["_FakeSMTP"] = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.messages = []
        self.started_tls = False
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, username, password):
        self.login_args = (username, password)

    def send_message(self, message):
        self.messages.append(message)


def test_channel_crud_requires_exec_or_admin(anon, session_factory):
    with session_factory() as session:
        _, mgr_key = seed_user(session, "mgr@x", role="manager", scope_type="team")
        _, exec_key = seed_user(session, "exec@x", role="exec", scope_type="global")
        session.commit()

    body = {"name": "Ops email", "type": "email", "target": "ops@example.com"}
    assert anon.get("/api/v1/alert-channels").status_code == 401
    assert anon.post("/api/v1/alert-channels", json=body).status_code == 401
    assert (
        anon.post("/api/v1/alert-channels", json=body, headers={"x-api-key": mgr_key}).status_code
        == 403
    )

    exec_headers = {"x-api-key": exec_key}
    created = anon.post("/api/v1/alert-channels", json=body, headers=exec_headers)
    assert created.status_code == 200, created.text
    channel = created.json()
    assert channel["type"] == "email"

    # Validation: bad email target / bad URL.
    assert (
        anon.post(
            "/api/v1/alert-channels",
            json={"name": "bad", "type": "email", "target": "not-an-address"},
            headers=exec_headers,
        ).status_code
        == 422
    )
    assert (
        anon.post(
            "/api/v1/alert-channels",
            json={"name": "bad", "type": "slack", "target": "ftp://x"},
            headers=exec_headers,
        ).status_code
        == 422
    )

    patched = anon.patch(
        f"/api/v1/alert-channels/{channel['id']}",
        json={"enabled": False, "name": "Ops email (off)"},
        headers=exec_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["enabled"] is False

    listed = anon.get("/api/v1/alert-channels", headers=exec_headers).json()
    assert listed["total"] == 1
    assert anon.delete(f"/api/v1/alert-channels/{channel['id']}", headers=exec_headers).status_code == 200


def test_rule_links_flow_through_api(anon, client, session_factory):
    with session_factory() as session:
        _, exec_key = seed_user(session, "exec2@x", role="exec", scope_type="global")
        session.commit()
    exec_headers = {"x-api-key": exec_key}

    channel = anon.post(
        "/api/v1/alert-channels",
        json={"name": "hook", "type": "webhook", "target": "http://hooks.test/chan"},
        headers=exec_headers,
    ).json()
    rule = anon.post(
        "/api/v1/alert-rules",
        json={
            "name": "linked rule",
            "metric": "error_rate",
            "warning_threshold": 0.4,
            "critical_threshold": 0.9,
            "channel_ids": [channel["id"]],
        },
        headers=exec_headers,
    )
    assert rule.status_code == 200, rule.text
    assert rule.json()["channel_ids"] == [channel["id"]]

    # Unknown/disabled channels are rejected.
    assert (
        anon.post(
            "/api/v1/alert-rules",
            json={
                "name": "bad link",
                "metric": "error_rate",
                "warning_threshold": 0.4,
                "critical_threshold": 0.9,
                "channel_ids": ["nope"],
            },
            headers=exec_headers,
        ).status_code
        == 404
    )
    anon.patch(
        f"/api/v1/alert-channels/{channel['id']}", json={"enabled": False}, headers=exec_headers
    )
    assert (
        anon.post(
            "/api/v1/alert-rules",
            json={
                "name": "disabled link",
                "metric": "error_rate",
                "warning_threshold": 0.4,
                "critical_threshold": 0.9,
                "channel_ids": [channel["id"]],
            },
            headers=exec_headers,
        ).status_code
        == 409
    )


def test_rule_channels_win_over_fallback(monkeypatch, session_factory, project):
    get_settings.cache_clear()
    monkeypatch.setattr(get_settings(), "alert_webhook_url", "http://fallback.test/alerts")
    sent: list[dict] = []
    _capture_urlopen(monkeypatch, sent)

    with session_factory() as session:
        for rule in session.query(AlertRule).all():
            rule.enabled = False
        channel = AlertChannel(
            type="webhook", name="chan", target="http://hooks.test/chan", enabled=True
        )
        session.add(channel)
        session.flush()
        rule = AlertRule(
            name="routed",
            metric="error_rate",
            warning_threshold=0.4,
            critical_threshold=0.9,
            scope_type="global",
        )
        session.add(rule)
        session.flush()
        session.execute(
            alert_rule_channels.insert(),
            [{"rule_id": rule.id, "channel_id": channel.id}],
        )
        now = datetime.now(timezone.utc)
        for _ in range(6):
            _add_execution(session, project, started=now)
        session.commit()
        created = evaluate_alerts(session)
        session.commit()

    assert created, "expected the routed error-rate alert"
    urls = [entry["url"] for entry in sent]
    # warning + critical each deliver to the linked channel.
    assert set(urls) == {"http://hooks.test/chan"}, sent
    assert all("alerts" in entry["payload"] for entry in sent)
    get_settings.cache_clear()


def test_fallback_used_when_channel_disabled_or_deleted(monkeypatch, session_factory, project):
    get_settings.cache_clear()
    monkeypatch.setattr(get_settings(), "alert_webhook_url", "http://fallback.test/alerts")
    sent: list[dict] = []
    _capture_urlopen(monkeypatch, sent)

    with session_factory() as session:
        for rule in session.query(AlertRule).all():
            rule.enabled = False
        channel = AlertChannel(
            type="slack", name="off", target="http://hooks.test/slack", enabled=False
        )
        session.add(channel)
        session.flush()
        rule = AlertRule(
            name="routed-off",
            metric="error_rate",
            warning_threshold=0.4,
            critical_threshold=0.9,
            scope_type="global",
        )
        session.add(rule)
        session.flush()
        session.execute(
            alert_rule_channels.insert(),
            [{"rule_id": rule.id, "channel_id": channel.id}],
        )
        now = datetime.now(timezone.utc)
        for _ in range(6):
            _add_execution(session, project, started=now)
        session.commit()
        created = evaluate_alerts(session)
        session.commit()

    assert created
    assert [entry["url"] for entry in sent] == ["http://fallback.test/alerts"], sent
    get_settings.cache_clear()


def test_slack_and_email_senders(monkeypatch, session_factory, project):
    get_settings.cache_clear()
    settings = get_settings()
    monkeypatch.setattr(settings, "alert_webhook_url", None)
    monkeypatch.setattr(settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(settings, "smtp_from", "alerts@example.com")
    monkeypatch.setattr(settings, "smtp_username", "user")
    monkeypatch.setattr(settings, "smtp_password", "pass")
    sent: list[dict] = []
    _capture_urlopen(monkeypatch, sent)
    _FakeSMTP.instances = []
    monkeypatch.setattr(notify.smtplib, "SMTP", _FakeSMTP)

    with session_factory() as session:
        for rule in session.query(AlertRule).all():
            rule.enabled = False
        slack = AlertChannel(
            type="slack", name="slack", target="http://hooks.test/slack", enabled=True
        )
        email = AlertChannel(
            type="email", name="email", target="ops@example.com", enabled=True
        )
        session.add_all([slack, email])
        session.flush()
        rule = AlertRule(
            name="multi",
            metric="error_rate",
            warning_threshold=0.4,
            critical_threshold=0.9,
            scope_type="global",
        )
        session.add(rule)
        session.flush()
        session.execute(
            alert_rule_channels.insert(),
            [
                {"rule_id": rule.id, "channel_id": slack.id},
                {"rule_id": rule.id, "channel_id": email.id},
            ],
        )
        now = datetime.now(timezone.utc)
        for _ in range(6):
            _add_execution(session, project, started=now)
        session.commit()
        created = evaluate_alerts(session)
        session.commit()

    assert created
    assert set(entry["url"] for entry in sent) == {"http://hooks.test/slack"}
    assert all("text" in entry["payload"] for entry in sent)
    assert _FakeSMTP.instances, "expected an SMTP session"
    smtp = _FakeSMTP.instances[0]
    assert smtp.started_tls
    assert smtp.login_args == ("user", "pass")
    assert smtp.messages and all(m["To"] == "ops@example.com" for m in smtp.messages)
    get_settings.cache_clear()


def test_email_without_smtp_config_is_skipped(monkeypatch, session_factory, project):
    get_settings.cache_clear()
    settings = get_settings()
    monkeypatch.setattr(settings, "alert_webhook_url", None)
    monkeypatch.setattr(settings, "smtp_host", None)
    monkeypatch.setattr(settings, "smtp_from", None)
    _FakeSMTP.instances = []
    monkeypatch.setattr(notify.smtplib, "SMTP", _FakeSMTP)

    with session_factory() as session:
        for rule in session.query(AlertRule).all():
            rule.enabled = False
        email = AlertChannel(
            type="email", name="email", target="ops@example.com", enabled=True
        )
        session.add(email)
        session.flush()
        rule = AlertRule(
            name="unconfigured-email",
            metric="error_rate",
            warning_threshold=0.4,
            critical_threshold=0.9,
            scope_type="global",
        )
        session.add(rule)
        session.flush()
        session.execute(
            alert_rule_channels.insert(),
            [{"rule_id": rule.id, "channel_id": email.id}],
        )
        now = datetime.now(timezone.utc)
        for _ in range(6):
            _add_execution(session, project, started=now)
        session.commit()
        created = evaluate_alerts(session)
        session.commit()

    # Evaluation succeeds even though the email cannot be sent.
    assert created
    assert not _FakeSMTP.instances
    get_settings.cache_clear()
