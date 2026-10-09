# 06 — Backend: alert rules model, CRUD, evaluation refactor

Type: task
Status: resolved
Blocked by: —
Area: audit item 7 (alerts)
Estimate: L

## Goal

Turn the env-driven threshold engine into DB-backed, configurable,
scope-aware alert rules that managers can create for their org units, with
warning + critical thresholds per rule. Preserve existing behavior (KPI gate)
by seeding the current built-in rules from settings.

## Changes

1. **Model + migration** (`models.py`, one Alembic revision):
   `alert_rules` — `id` String(32) PK, `name` String(120),
   `metric` String(40) (`error_rate|daily_tokens|tool_calls_per_execution|p95_latency|cost_anomaly`),
   `warning_threshold` Numeric(18,6), `critical_threshold` Numeric(18,6),
   `scope_type` String(20) (`global|department|team|project`), `scope_id`
   String(32) nullable, `enabled` Boolean default true, `builtin` Boolean
   default false, `created_by` String(32) nullable, `created_at`.
   Indexes: `(enabled)`, `(scope_type, scope_id)`.
   Also `alerts.rule_ref` String(32) nullable + index (anchor for ack scoping).
2. **Seeding** (`seed.py`, called from `main._lifespan`):
   if `alert_rules` is empty, insert the five built-in rules from
   `Settings.alert_*` (global scope, `builtin=True`) so the current behavior and
   the KPI gate keep passing. Idempotent.
3. **Evaluation refactor** (`alerts.py`):
   - `evaluate_threshold_rules(session, now)` iterates **enabled DB rules**;
     for each rule resolve its project set (global → all projects; scoped →
     `allowed_project_ids`-style resolution for that scope) and compute the
     metric over the current UTC day restricted to that slice.
   - Emit warning and/or critical alerts using the rule's own thresholds;
     dedupe per `(rule_ref, day, severity)`; message includes rule name, value,
     threshold, scope and day.
   - Keep `alert_min_executions` as a global sanity guard for ratio metrics.
   - `evaluate_alerts` keeps budget evaluation; `_notify_webhook` remains the
     delivery stub for this ticket (channels in ticket 07).
4. **CRUD** (`new file api/routes/alert_rules.py`):
   - `GET /alert-rules` (scoped: admin/exec all; manager sees rules whose scope
     is inside their coverage or global), `POST /alert-rules`,
     `PATCH /alert-rules/{id}`, `DELETE /alert-rules/{id}`.
   - Authorization: admin key/admin session/exec → any rule incl. global;
     manager → only rules whose scope they cover (`covers_scope`); global rule
     create → 403 for managers.
   - Validation: metric must be known (422); `critical_threshold >= warning_threshold`
     (422); scope must exist and match the role's allowed scopes
     (`normalize_role_scope` reuse where applicable).
   - Deleting a `builtin` rule → 409 "system rule: disable it instead"
     (`enabled=false` via PATCH is allowed).
   - Responses include `scope_name` (department/team/project label) for the UI.
5. **KPI gate**: unchanged assertions; confirm the seeded rules reproduce the
   previous alert behavior (the gate's non-budget alert scenario still fires).

## Acceptance

- Empty `alert_rules` table on startup → seeded built-ins; second startup does
  not duplicate.
- Manager creates `error_rate` warning=0.4/critical=0.8 for their team; an
  execution burst in that team raises the expected alerts after evaluation;
  executions in other teams do not.
- Manager cannot create/edit/delete a global rule (403); admin can.
- Disabling a built-in rule stops its alerts; deleting it returns 409.
- `POST /alerts/evaluate` and the 60 s loop use DB rules only.
- Inverted thresholds / unknown metric → 422.

## Tests

- New `backend/tests/test_alert_rules.py`:
  - seeding idempotence; CRUD matrix (admin/exec/manager/out-of-scope);
    validation 422s; builtin delete 409 + disable path;
  - evaluation: scoped rule fires only for its projects; warning vs critical;
    dedupe per day; disabled rule silent;
  - regression: the five seeded rules reproduce the old env-threshold behavior
    (see `test_alert_rules.py`/`kpi_gate.py` coverage).
- `uv run pytest -q`, ruff, mypy; migration upgrade/downgrade fresh DB.

## Comments

Implemented. New `alert_rules` table (migration `c9e3f2a51b7d`) + `alerts.rule_ref`
anchor; five built-in rules seeded idempotently at startup from the historical
env thresholds (warning = env, critical = 2×, matching the old `_severity`), so
existing behavior is preserved. `evaluate_threshold_rules` now reads enabled DB
rules, resolves each rule's scope (global/department/team/project) to its
project set, computes the metric over that slice, and emits warning/critical
alerts deduped per `(rule, day, severity)` with `rule_ref` set. New CRUD
(`GET/POST/PATCH/DELETE /alert-rules`): admin/exec manage any rule, managers
only scoped ones they cover (global → 403), built-ins reject deletion (409) but
can be disabled/edited; responses include `scope_name`.

Evidence: new `tests/test_alert_rules_crud.py` (4 tests: seeding, manager CRUD
matrix incl. sibling/global 403s + validation 422/404 + builtin 409, scoped
evaluation with cross-team isolation and dedupe, disabled-rule silence);
existing `test_alert_rules.py` updated to the metric dimension keys. Full
backend suite **127 passed**; ruff + mypy clean; migration upgrade/check/
downgrade/upgrade verified. **KPI gate 28/28 with "alert rules" PASSED** against
a disposable DB (port 8123).
