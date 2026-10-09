"""Alert delivery: email (SMTP) + Slack/webhook channels (audit item 7).

Best-effort by design: every sender failure is logged and never propagates into
alert evaluation. Rules with linked channels deliver to exactly those; rules
(and budget alerts) without links fall back to ``AIOBS_ALERT_WEBHOOK_URL`` as a
single batched POST, preserving the F37 behavior.
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
from .models import Alert, AlertChannel, alert_rule_channels

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


def _post_json(url: str, payload: dict, timeout: float) -> None:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout):
        pass


def _send_email(channel: AlertChannel, alert: Alert, settings) -> None:
    if not settings.smtp_host or not settings.smtp_from:
        logger.warning(
            "email channel %r skipped: AIOBS_SMTP_HOST/AIOBS_SMTP_FROM not set",
            channel.name,
        )
        return
    message = EmailMessage()
    message["Subject"] = f"[{alert.severity.upper()}] {alert.message[:140]}"
    message["From"] = settings.smtp_from
    message["To"] = channel.target
    message.set_content(
        f"{alert.message}\n\n"
        f"Severity: {alert.severity}\n"
        f"Triggered: {alert.triggered_at.isoformat() if alert.triggered_at else ''}\n"
    )
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
        _send_email(channel, alert, settings)
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
    """Route created alerts to their channels; never raise."""
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
            except Exception:
                logger.warning(
                    "alert delivery failed via %s channel %r",
                    channel.type,
                    channel.name,
                    exc_info=True,
                )
    if fallback and settings.alert_webhook_url:
        try:
            _post_json(
                settings.alert_webhook_url,
                {"alerts": [_alert_payload(a) for a in fallback]},
                settings.alert_webhook_timeout_s,
            )
        except Exception:
            logger.warning("alert webhook delivery failed", exc_info=True)
