# 06 — Docs + verification

Type: task
Status: resolved
Blocked by: 01–05
Area: margin, docs
Estimate: S

## Goal

The new surface is documented and the whole change set is verified end to end.

## Changes

1. **`docs/06-project-audit.md`** — audit entries: versioned rates, `/margin`,
   the model-row fix, the Executive margin surface and the removal of the exec
   latency panels; ADR-0005 gains a pointer to ADR-0013.
2. **`plans/roles.md`** — already updated in ticket 01; verify the wording.
3. **Verification** — backend `pytest` + `ruff` + `mypy` (migration applies on
   the dev DB), frontend `vitest` + coverage + `lint` + `build`, then a live
   pass as `exec@local` on the rebuilt stack with two rate versions seeded so
   the step and the break-even number are real.

## Acceptance

- All suites green; the live stack shows revenue, margin, coverage and
  break-even for a project with two versions, and "no rate" for the rest.

## Tests

- Full backend and frontend suites plus the live smoke through the dashboard
  proxy.

## Result

- Docs: ADR-0013 (+ the internal-project decision), `plans/roles.md`,
  `CONTEXT.md` glossary, `docs/06` F53–F57.
- Suites: backend `ruff` + `mypy` + `pytest`, frontend `vitest` + coverage +
  `lint` + `build`, both green; migrations applied on the dev DB.
- Live: `exec@local` sees the margin surface with two rate versions seeded (a
  mid-window step), an internal project reported separately, and the
  break-even multiple; Manager keeps its latency panels.
