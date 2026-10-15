# 03 — Backend: retire the client attribution dimension

Type: task
Status: resolved
Blocked by: 02
Area: refinements v3, client dimension (ADR-0011)
Estimate: L

## Goal

Remove the client data dimension everywhere in the backend: schema, ingest,
dimensions, routes, budgets, alerts and scripts — destructively, following the
ADR-0006 precedent.

## Changes

1. **Schema (one migration)**
   - Drop `clients` table; drop `executions.client_id` and `budgets.client_id`
     (with their indexes/FKs); delete `daily_metrics` rows where
     `dimension = 'client'`.
   - Downgrade recreates the table/columns empty (best effort, no data).
2. **Models** (`models.py`) — delete `Client`; drop both `client_id` columns.
3. **Ingest** (`ingest/pipeline.py`) — drop `_upsert_client` and the
   `execution.client_id` assignment; the root's `sdk.client_id` attribute is no
   longer read or stored.
4. **Analytics** (`analytics.py`) — `DIMENSIONS` loses `client`; the daily
   rollup drops the client bucket.
5. **Queries/serialization** (`api/queries.py`, `api/serialize.py`) —
   `EXTERNAL = (Execution, Project.project_id)`; `exec_aggregates`/`exec_rows`
   lose the client join and the `client_id` filter; `execution_dict` loses
   `client_id`.
6. **Routes**
   - Delete `api/routes/clients.py` and its router registration.
   - `/costs`: `DIMENSIONS` drops `client`; fallback keys drop
     `{"client": "unattributed"}`.
   - `/metrics`: `DIMENSIONS` drops `client`; the scoped-dimension guard
     becomes `{"workflow", "team"}`.
   - `/executions`, `/workflows`, `/agents`: drop the `client_id` query param
     and filter plumbing.
7. **Budgets** (`api/routes/budgets.py`, `alerts.py`) — drop the `client`
   payload field, `_resolve_scope` client branch, `_name_maps` clients,
   `_scope_type` client label, and the `budget_spend` client filter; budget
   scopes are project/department/team (+global exec/admin).
8. **Seed/scripts** — `seed.py` drops demo clients; `scripts/e2e_smoke.py`
   drops the `sdk.client_id` attribute and the `/api/v1/clients` check;
   `scripts/kpi_gate.py` drops the `sdk.client_id` attribute and the
   `client_id` detail assertion (use project instead).
9. **Tests** — update every dimension-touching suite (`test_cost_history`,
   `test_series`, `test_agents`, `test_search_sort`, `test_budgets`,
   `test_metadata_redaction`, `conftest` fixtures); keep the RBAC client-role
   suites (`test_rbac`, `test_client_access`, `test_auth`) untouched.

## Acceptance

- `grep -rn "client_id\|Client" backend/src` shows only the RBAC `client` role
  vocabulary (`ROLES`, `ROLE_SCOPES`, `cost_visible`, `require_access(...)`).
- `POST /api/v1/traces` with a root carrying `sdk.client_id` ingests cleanly and
  stores no client anywhere.
- `/costs` and `/metrics` reject `dimension=client` with 422.
- Budget create/update rejects a `client` field; dept/team/project scopes and
  the alerts budget path still work.
- Migration upgrade/downgrade/`alembic check` clean on the dev DB.

## Tests

- `uv run pytest -q` (full suite green), `ruff`, `mypy`.
- Migration round-trip on a fresh database and against the dev database.

## Comments

Done. Removed `Client`/`clients`, `executions.client_id`, `budgets.client_id`,
the `daily_metrics` client rows (migration `c3d91b7f5a24`, destructive, with a
schema-only downgrade), the `/clients` router, `dimension=client` in
`/costs`+`/metrics`+analytics, the budget `client` scope/labels, the alerts
client spend filter, `_upsert_client`, and the client queries in
executions/workflows/overview. `EXTERNAL` is now
`(Execution, Project.project_id, Project.name)` and `execution_dict` no longer
carries `client_id`. Scripts (`e2e_smoke.py`, `kpi_gate.py`) assert project
attribution instead (`detail["project_id"] == PROJECT_ID`,
`project_name == "KPI Gate"`). `tests/test_upsert_race.py` (the F27 helper test)
retargeted from the deleted client upsert to `_upsert_row`/`ProjectKey`, and a
new `test_client_dimension_is_gone` proves a legacy `sdk.client_id` root still
ingests while `/costs|/metrics?dimension=client` return 422 and `/clients`
404s.

Evidence: **146 passed**; `ruff` clean; `mypy` clean (41 files); migration
round-trip on a scratch DB (`upgrade head` → `alembic check` "No new upgrade
operations detected" → `downgrade -1` → `upgrade head`).
