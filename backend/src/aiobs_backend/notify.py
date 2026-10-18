"""Alert delivery: email (SMTP) + Slack/webhook channels (audit item 7).

Best-effort by design: every sender failure is logged and never propagates into
alert evaluation, but each attempt is recorded in ``alert_deliveries`` so the
dashboard can show a delivery history and per-channel test results
(refinements v2).
"""
from __future__ import annotations

import json
import logging
import smtplib
import urllib.request
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import Alert, AlertChannel, AlertDelivery, alert_rule_channels

logger = logging.getLogger(__name__)


def _alert_payload(alert: Alert) -> dict:
    return {
        "id": alert.id,
        "rule_id": alert.rule_id,
        "rule_ref": alert.rule_ref,
        "severity": alert.severity,
        "message": alert.message,
        "dimension": alert.dimension,
        "dimension_key": alert.dimension_key,
        "status": alert.status,
        "triggered_at": alert.triggered_at.isoformat() if alert.triggered_at else None,
    }


def channels_for_alert(session: Session, alert: Alert) -> list[AlertChannel]:
    """Enabled channels linked to the alert's rule (empty = use the fallback)."""
    if not alert.rule_ref:
        return []
    return list(
        session.execute(
            select(AlertChannel)
            .join(
                alert_rule_channels,
                alert_rule_channels.c.channel_id == AlertChannel.id,
            )
            .where(
                alert_rule_channels.c.rule_id == alert.rule_ref,
                AlertChannel.enabled.is_(True),
            )
        )
        .scalars()
        .all()
    )


def _record(
    session: Session,
    *,
    alert_id: str | None,
    channel_id: str | None,
    channel_type: str,
    target: str,
    ok: bool,
    error: str | None = None,
) -> None:
    session.add(
        AlertDelivery(
            alert_id=alert_id,
            channel_id=channel_id,
            channel_type=channel_type,
            target=target,
            status="sent" if ok else "failed",
            error=error,
        )
    )


def _post_json(url: str, payload: dict, timeout: float) -> None:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout):
        pass


def _send_email_message(
    target: str, settings, *, subject: str, body: str
) -> None:
    if not settings.smtp_host or not settings.smtp_from:
        raise RuntimeError("SMTP is not configured (AIOBS_SMTP_HOST/AIOBS_SMTP_FROM)")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from
    message["To"] = target
    message.set_content(body)
    with smtplib.SMTP(
        settings.smtp_host, settings.smtp_port, timeout=settings.alert_webhook_timeout_s
    ) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password or "")
        smtp.send_message(message)


def _send_channel(channel: AlertChannel, alert: Alert, settings) -> None:
    if channel.type == "email":
        _send_email_message(
            channel.target,
            settings,
            subject=f"[{alert.severity.upper()}] {alert.message[:140]}",
            body=(
                f"{alert.message}\n\n"
                f"Severity: {alert.severity}\n"
                f"Triggered: {alert.triggered_at.isoformat() if alert.triggered_at else ''}\n"
            ),
        )
    elif channel.type == "slack":
        _post_json(
            channel.target,
            {"text": f"[{alert.severity.upper()}] {alert.message}"},
            settings.alert_webhook_timeout_s,
        )
    else:  # webhook
        _post_json(
            channel.target,
            {"alerts": [_alert_payload(alert)]},
            settings.alert_webhook_timeout_s,
        )


def deliver(session: Session, alerts: list[Alert]) -> None:
    """Route created alerts to their channels; never raise. Attempts are recorded."""
    if not alerts:
        return
    settings = get_settings()
    fallback: list[Alert] = []
    for alert in alerts:
        try:
            channels = channels_for_alert(session, alert)
        except Exception:
            logger.warning("channel lookup failed", exc_info=True)
            channels = []
        if not channels:
            fallback.append(alert)
            continue
        for channel in channels:
            try:
                _send_channel(channel, alert, settings)
            except Exception as exc:
                logger.warning(
                    "alert delivery failed via %s channel %r",
                    channel.type,
                    channel.name,
                    exc_info=True,
                )
                _record(
                    session,
                    alert_id=alert.id,
                    channel_id=channel.id,
                    channel_type=channel.type,
                    target=channel.target,
                    ok=False,
                    error=str(exc) or exc.__class__.__name__,
                )
            else:
                _record(
                    session,
                    alert_id=alert.id,
                    channel_id=channel.id,
                    channel_type=channel.type,
                    target=channel.target,
                    ok=True,
                )
    if fallback and settings.alert_webhook_url:
        try:
            _post_json(
                settings.alert_webhook_url,
                {"alerts": [_alert_payload(a) for a in fallback]},
                settings.alert_webhook_timeout_s,
            )
        except Exception as exc:
            logger.warning("alert webhook delivery failed", exc_info=True)
            for alert in fallback:
                _record(
                    session,
                    alert_id=alert.id,
                    channel_id=None,
                    channel_type="webhook",
                    target=settings.alert_webhook_url,
                    ok=False,
                    error=str(exc) or exc.__class__.__name__,
                )
        else:
            for alert in fallback:
                _record(
                    session,
                    alert_id=alert.id,
                    channel_id=None,
                    channel_type="webhook",
                    target=settings.alert_webhook_url,
                    ok=True,
                )


def send_test(session: Session, channel: AlertChannel) -> tuple[bool, str | None]:
    """Send a test notification through one channel and record the attempt."""
    settings = get_settings()
    subject = "Test alert from AI Observability Platform"
    body = (
        f"This is a test notification for channel “{channel.name}”. "
        "If you can read this, the channel is configured correctly."
    )
    try:
        if channel.type == "email":
            _send_email_message(channel.target, settings, subject=subject, body=body)
        elif channel.type == "slack":
            _post_json(
                channel.target,
                {"text": f"[TEST] {subject}: {body}"},
                settings.alert_webhook_timeout_s,
            )
        else:
            _post_json(
                channel.target,
                {"test": True, "message": body},
                settings.alert_webhook_timeout_s,
            )
    except Exception as exc:
        error = str(exc) or exc.__class__.__name__
        _record(
            session,
            alert_id=None,
            channel_id=channel.id,
            channel_type=channel.type,
            target=channel.target,
            ok=False,
            error=error,
        )
        return False, error
    _record(
        session,
        alert_id=None,
        channel_id=channel.id,
        channel_type=channel.type,
        target=channel.target,
        ok=True,
    )
    return True, None
