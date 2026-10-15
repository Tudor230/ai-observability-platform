# Refinements v3 — project identity, attribution and table UX

Status: in progress (2026-10-15)
Source: follow-up review round after refinements v2 (project identity, client
dimension retirement, per-table filtering, table/dropdown ergonomics)
Convention: phase-ordered commits, one per ticket, on `feat/refinements`.

## Settled decisions (planning session, 2026-10-15)

1. **`project_id` is server-generated** (opaque `p_<hex>`) and is never rendered
   by the dashboard. It stays the technical token in FE URLs/query params and
   API payloads — decision: *hide from the UI only* (no FE API churn).
2. **Project `name` is the unique human handle** — globally unique across
   projects; it is what every picker, chip, table and title shows.
3. **The `client` data dimension is retired end to end.** No `client_id` in the
   SDK, in traces, in the backend schema, or in dashboard breakdowns; client
   breakdowns become project breakdowns. The RBAC **`client` role** is
   unrelated and must stay untouched (see ADR-0011).
4. **SDK**: `client_id` is hard-removed; `project_id` survives only as a
   debug/test override (documented and warned as not-for-production); the
   examples use API keys only. This is a breaking SDK change → `sdk-v0.2.0`
   (see ADR-0012). No `project_name` parameter is introduced.
5. **Manager and Executive cost cards become two-view cards** — breakdown (bars)
   and detail (table) — switched with the existing `Tabs` component. Detail
   rows come from an extended `/costs` response; no new endpoints.
6. **Cost/breakdown tables get a height cap** (sticky header + scroll) and
   client-side pagination at 10 rows, via a shared `Pagination` component
   extracted from Engineering. Engineering keeps its server-side pager.
7. **Filtering becomes per-table**: the page-level `days` stays shared; each
   card gets its own control, its own chips, its own query key, and namespaced
   URL params so views stay shareable and drill-down links keep working.
8. **Entity pickers** (project/team/department/scope/model) become searchable,
   height-capped, scrolling comboboxes (`SearchableSelect`); small enums
   (status, severity, rows-per-page) stay native selects.
9. **Out of scope**: the `/api/v1/metrics` cost-visibility leak (client-only
   callers can still read `total_cost`) — tracked separately.

## Tickets

| # | Phase | Scope |
|---|---|---|
| 01 | 0 | Docs: ADR-0011 (retire client dimension), ADR-0012 (project identity), spec + tickets, `CONTEXT.md` glossary |
| 02 | 1 | Backend: generated `project_id`, globally unique `name`, `project_name` in execution payloads |
| 03 | 1 | Backend: retire the client dimension (schema, dimensions, routes, ingest, budgets, alerts, scripts, tests) |
| 04 | 1 | Backend: rich `/costs` rows (error rate, avg duration, last seen, tokens) for the detail views |
| 05 | 2 | SDK: drop `client_id`; debug-only `project_id` override; key-only examples/READMEs |
| 06 | 2 | SDK: version `0.2.0` + release (`sdk-v0.2.0` tag) |
| 07 | 3 | Frontend: stop rendering `project_id`; project names everywhere |
| 08 | 3 | Frontend: retire the client dimension from filters, tables and pages |
| 09 | 3 | Frontend: two-view cost cards, capped/paged tables, shared `Pagination` |
| 10 | 3 | Frontend: per-table filters with namespaced URL state |
| 11 | 3 | Frontend: searchable entity pickers |
| 12 | 4 | Docs sweep (plans, docs/03–06, READMEs) + full verification gate |

## Design notes

- **Generated id**: `p_` + 12 lowercase hex, emitted at creation time in the
  same place the row is created (`api/routes/projects.py` for the admin path,
  request approval for the self-service path). It keeps every existing
  behaviour: URL path token (`/api/v1/projects/{project_id}/keys`), FE filter
  param, `x-project-name` assertion, `daily_metrics.dimension_key`, budget
  `project` payloads, membership project scope.
- **Name uniqueness**: `Project.name` gets a global unique index; duplicates are
  rejected with 409 on creation and on rename-less flows. Pre-migration audit
  showed no duplicates in the live DB.
- **Client-dimension inventory** (must all go): `Client` model + `clients`
  table, `executions.client_id`, `budgets.client_id`, `daily_metrics` client
  rows, `analytics.DIMENSIONS`, ingest `_upsert_client`, `queries.EXTERNAL`,
  `serialize.execution_dict.client_id`, `costs.DIMENSIONS`/`_GROUP_COLUMNS`,
  `metrics.DIMENSIONS`, the budget `client` scope + `_scope_type`,
  `alerts.budget_spend` client filter, `api/routes/clients.py`, seed data,
  `scripts/kpi_gate.py`, `scripts/e2e_smoke.py`, and the client-touching tests.
- **Detail views** reuse `/costs`: rows gain `failed_executions`, `error_rate`,
  `avg_duration_ms`, `last_seen`, `total_tokens` (the shape `/clients` already
  returned through `exec_aggregates`) while keeping `tokens` for the existing
  breakdown consumers.
- **FE filter params**: page-level `days`; per card `<card>_<field>`, e.g.
  `projects_project`, `workflows_workflow`, `teams_team`, `models_model`.
  Engineering keeps its existing `q`/`status`/`sort`/`order`/`page`/`limit`.
- **Drill-down links** that currently target `?workflow=`/`?client_id=` move to
  the namespaced params of the card they open.

## Verification

- Backend: `pytest` + `ruff` + `mypy`; migration upgrade / `alembic check` /
  downgrade / re-upgrade on the dev database.
- SDK: full suite + coverage floor (`pytest --cov … --cov-fail-under=80`);
  mock CLI and e2e paths unchanged.
- Frontend: `vitest` with the 80% coverage gate, lint, build.
- End of run: `scripts/e2e_smoke.py` and `scripts/kpi_gate.py` green, plus a
  manual pass on the running compose stack (login, Overview/Manager/Executive/
  Projects/Requests/Alerts pages).
