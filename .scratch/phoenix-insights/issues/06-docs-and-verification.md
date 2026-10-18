# 06 — Docs + verification gate

Type: task
Status: in progress
Blocked by: 01–05
Area: phoenix insights, docs
Estimate: S

## Goal

The new surface is documented and the whole change set is verified end to end.

## Changes

1. **`docs/06-project-audit.md`** — audit entries for the new read endpoints
   (model insights, tool insights), the stat-row changes and the table overflow
   rule.
2. **`CONTEXT.md`** — glossary: *Model insights*, *Tool insights*, *unit cost*.
3. **Verification** — backend `pytest` + `ruff` + `mypy`; frontend `vitest` with
   the coverage gate, `lint`, `build`; live pass with the manager account and a
   fresh `exec@local` login on the rebuilt compose stack (Executive is
   exec-only).

## Acceptance

- Docs list the new endpoints with their row shapes and access rules.
- All suites green; the live stack serves the new bundle and both role pages
  render their sections.

## Tests

- Full backend and frontend suites plus the live smoke through the dashboard
  proxy.
