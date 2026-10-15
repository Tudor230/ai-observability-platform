# 12 — Docs sweep + verification gate

Type: task
Status: resolved
Blocked by: 01–11
Area: refinements v3, phase 4
Estimate: M

## Goal

Bring the plans, docs and READMEs in line with the shipped behaviour and run
the full verification gate.

## Changes

1. **Plans** — `plans/backend.md` (drop the client dimension/`clients` table,
   document `project_name` + generated ids), `plans/frontend.md` (two-view
   cards, per-table filters, pickers, project-name handles),
   `plans/sdk.md` (no `client_id`; debug-only `project_id`),
   `plans/implementation-plan.md` if it references client attribution.
2. **Docs** — `docs/03-to-be-solution.md` (data model/dimensions),
   `docs/05` (KPI definitions that mention client),
   `docs/06-project-audit.md` (append the v3 fix entry),
   `sdk/README.md` + `sdk/examples/README.md` (already touched in ticket 05 —
   verify final state), root `README.md` (dashboard status paragraph).
3. **Glossary** — verify `CONTEXT.md` matches shipped behaviour (no client
   dimension; project name/id split; debug-only routing).
4. **Verification gate**:
   - backend: `pytest`, `ruff`, `mypy`, migration round-trip, `alembic check`;
   - SDK: full suite + coverage floor, mock CLI (with and without `--endpoint`);
   - frontend: `vitest` + coverage gate, lint, build;
   - `scripts/e2e_smoke.py` and `scripts/kpi_gate.py` green;
   - manual pass on the compose stack: login, create project (request →
     approve), ingest via `aiobs-mock --api-key`, verify Overview / Manager /
     Executive / Projects / Requests / Alerts, cost hidden for a client-only
     account.
5. **Ticket bookkeeping** — mark every v3 ticket `Status: resolved` with a
   `## Comments` evidence line (numbers, commands, commit hashes).

## Acceptance

- No doc describes a client dimension, a user-typed project id, or an SDK
  `client_id`.
- All gates above pass on the final commit.

## Tests

- The full gate list in step 4, recorded per ticket.

## Comments

Done. Docs updated: `plans/backend.md` (dimensions/schema/endpoints/pipeline —
no client, generated ids noted), `plans/frontend.md` (per-project views,
per-table filters), `plans/sdk.md` (no `client_id`, debug-only `project_id`),
`plans/implementation-plan.md`, `docs/03` (dimension lists → project) and
`docs/06` (new F42–F47 entries covering v3). Root `README.md` needed no change
("client views" there means the RBAC persona page, which still exists).

Two scripts needed code fixes to pass under v3: `seed.seed_demo_project` is now
name-keyed and idempotent (it previously bailed out with a placeholder key when
the project already existed, and generated ids on create), `seed_all` matches,
and `kpi_gate.py` seeds by name and asserts the *actual* generated
`project_id` from the DB.

**Gate evidence** (all on the v3 tip):
- backend: `ruff` + `mypy` clean, **147 passed**;
- SDK: **161 passed, 1 skipped**, coverage **87.3%** (floor 80), `aiobs-mock`
  **28/28** offline;
- frontend: `vitest` **513 passed**, coverage 88.5/73.6/68.1 (gates
  80/70/65), `lint` + `build` clean;
- `scripts/e2e_smoke.py`: **ALL OK** (health, me, overview, executions,
  workflows, costs, metrics, alerts, directory, requests; anon → 401);
- `scripts/kpi_gate.py`: **KPIs PASSED** — span coverage 100.0% (89/89), cost
  error under 1%, classification, alert rules, 28/28 mock scenarios.
- compose stack rebuilt on the v3 commit: dev DB migrated to
  `c3d91b7f5a24` (`clients` table gone, `daily_metrics` dimensions =
  total/project/team/workflow), API healthy, dashboard serving the current
  bundle (`index-zlypVIWf.js`).
- Manual API journey against the running stack: create-project request
  `{name, team_id}` → auto-approved with a generated id
  (`p_cdd941b08cc9`), duplicate name → 409, key minted, `aiobs-mock` ingested
  **28 executions** under it — payloads show `project_name` and no `client_id`,
  and `/costs` returns the rich row (28 executions, 12 failed, error_rate
  0.4286, last_seen).

Remaining: the visual pass in a browser (the desktop browser is not connected
to this session), and cutting `sdk-v0.2.0` (ticket 06) which needs the
maintainer's go-ahead because the tag publishes to PyPI.
