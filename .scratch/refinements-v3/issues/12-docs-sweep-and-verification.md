# 12 — Docs sweep + verification gate

Type: task
Status: open
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
