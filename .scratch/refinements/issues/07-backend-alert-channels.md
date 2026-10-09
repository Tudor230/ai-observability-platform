# 07 — Backend: alert channels (email/Slack/webhook) + per-rule routing

Type: task
Status: open
Blocked by: 06
Area: audit item 7 (alerts — channels)
Estimate: M

## Goal

Deliver alerts to real channels — email and chat (Slack-compatible webhook) —
selectable per rule, with the existing global webhook as fallback. Best-effort
delivery: failures are logged and never break evaluation.

## Changes

1. **Models + migration** (one Alembic revision):
   - `alert_channels` — `id`, `type` (`email|slack|webhook`), `name`,
     `target` (email address or URL), `enabled` default true, `created_by`,
     `created_at`.
   - `alert_rule_channels` — join table (`rule_id` → `alert_rules.id`,
     `channel_id` → `alert_channels.id`), unique pair, cascade on delete.
2. **Config** (`config.py`): `smtp_host|smtp_port|smtp_username|smtp_password|smtp_from|smtp_starttls`
   (all optional; email channel requires `smtp_host`+`smtp_from`).
3. **Delivery module** (`alerts/delivery.py`):
   - `deliver(session, created_alerts)`: for each alert resolve target channels
     — rule alerts with linked channels → those channels; rule alerts without
     links → fallback `AIOBS_ALERT_WEBHOOK_URL`; budget alerts → fallback
     webhook (unchanged).
   - Senders: `email` via stdlib `smtplib` (plain-text body: severity, message,
     triggered_at); `slack` posts `{"text": message}`; `webhook` posts the
     existing JSON payload `{"alerts": [...]}`.
   - Timeouts, one log line per failure, never raise.
   - `evaluate_alerts` calls `deliver` instead of `_notify_webhook` (keep the
     old function name as a thin wrapper or remove it; no callers left).
4. **Channel CRUD** (`api/routes/alert_channels.py`):
   - `GET/POST /alert-channels`, `PATCH/DELETE /alert-channels/{id}` —
     admin/exec only.
   - Validation: type enum (422); `email` target must look like an address;
     `slack|webhook` target must be `http(s)://…`; deleting a channel removes
     its rule links (cascade) — rules silently fall back to the global webhook.
5. **Rule↔channel wiring** (extends ticket 06):
   - `POST/PATCH /alert-rules` accept optional `channel_ids: [str]`; unknown or
     disabled channel → 422/409; replaced on PATCH; returned on GET.
6. **Docs/env** (`backend/README.md`): document SMTP vars and the channel
   routing/fallback rules.

## Acceptance

- With `AIOBS_SMTP_*` set and an email channel linked to a rule, a triggered
  alert attempts an email; with no SMTP configured the attempt is logged as a
  warning and evaluation still succeeds.
- A Slack-type channel posts `{"text": ...}` to its target; a webhook-type
  posts the alert JSON.
- A rule without linked channels still hits `AIOBS_ALERT_WEBHOOK_URL`.
- Deleting a channel leaves its rules working via fallback and does not error.
- Channel CRUD is 401/403 for non admin/exec.

## Tests

- New `backend/tests/test_alert_channels.py`:
  - CRUD auth matrix + validation 422s;
  - delivery routing: monkeypatched `smtplib.SMTP` and `urllib.request.urlopen`
    assert the right targets/payloads; fallback path when no channels;
    disabled channel skipped; sender exception swallowed;
  - cascade: deleting a channel clears rule links;
  - rules API round-trips `channel_ids`.
- `uv run pytest -q`, ruff, mypy; migration fresh-DB upgrade/downgrade.

## Comments
