# 08 — Backend: scoped alert acknowledgment + rule alert visibility

Type: task
Status: resolved
Blocked by: 06
Area: audit item 7 (alerts — manager ack)
Estimate: S

## Goal

Let covering managers acknowledge/close the alerts they can act on, keep
admin/exec global, expose rule alerts to scoped callers when the rule's scope
intersects theirs, and return a server-computed `can_ack` per alert.

## Changes

1. **Scope resolution helper** (`api/routes/alerts.py` or `api/queries.py`):
   `alert_scope(session, alert) -> tuple[str, str | None]`:
   - `dimension == "budget"` → the budget's scope (project, else team, else
     department; global budget → `global`);
   - `rule_ref` set → the referenced rule's `scope_type/scope_id`
     (`global` if absent/global);
   - else → `global`.
2. **`queries.alert_scope_clause` extension** (`api/queries.py`):
   - Rule alerts are visible to a scoped caller when the rule's scope
     intersects the caller's allowed set: project scope → project in allowed;
     team scope → team in allowed teams; department scope → department in
     allowed departments. Global rule alerts stay exec/admin-only.
   - Budget alerts keep their current project-following behavior.
   - Implement via `Alert.rule_ref` join or an `IN` subquery over `alert_rules`
     (single query per request, no N+1).
3. **`PATCH /alerts/{id}`** (`routes/alerts.py`):
   - Accept **admin key/admin session/exec/covering manager**: authorize with
     the helper from (1) using `covers_scope` semantics.
   - Allowed statuses stay `open|acknowledged|closed`; invalid → 400.
   - Out-of-scope → 403; unknown alert → 404.
4. **`GET /alerts` response**: add `can_ack: bool` per item (same coverage
   logic, cheap to compute since scopes are resolved anyway) and `scope`
   label (`budget:<project>|rule:<department|team|project|global>`) for display.

## Acceptance

- A team manager can ack a budget alert on their project and a rule alert whose
  rule covers their team; cannot ack a sibling team's alert (403).
- Admin/exec can ack any alert; clients cannot ack anything (`can_ack=false`,
  403 on PATCH).
- Scoped callers now see rule alerts whose scope intersects their access;
  global rule alerts remain exec/admin-only.
- Status transitions remain validated; unknown alert id → 404.

## Tests

- Extend `backend/tests/test_alert_rules.py` or new
  `test_alert_ack.py`: ack matrix (admin/exec/covering manager/sibling/manager
  on global/client), `can_ack` values in the list response, rule-alert
  visibility per scope, 404/400 paths.
- `uv run pytest -q`, ruff, mypy.

## Comments

Implemented. `PATCH /alerts/{id}` now uses `require_access()` and authorizes the
admin key/admin session, any global grant, or a manager covering the alert's
scope (budget → its project/team/department; rule → the rule's scope; global →
exec/admin only) with 403 otherwise. `GET /alerts` items gained
`can_ack` + `scope`/`scope_name`. `alert_scope_clause` now resolves budget
visibility through the budget's project/team/department (fixing a latent
comparison bug where budget ids were matched against project ids) and exposes
rule alerts whose rule scope intersects the caller's access; global rule alerts
stay exec/admin-only. `overview` passes the department/team sets too.

Evidence: new `tests/test_alert_ack.py` (manager ack matrix incl. sibling 403,
client sees-but-cannot-ack, exec/admin global ack, 400/404 paths, visibility
per scope). Full backend suite **135 passed**; ruff + mypy clean.
