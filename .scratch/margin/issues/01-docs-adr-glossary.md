# 01 — Docs: ADR-0013, roles matrix, glossary, spec

Type: docs
Status: resolved
Area: margin, bookkeeping
Estimate: S

## Goal

Record the decision to reverse ADR-0005's margin descope and define the exact
semantics of the new inputs before code lands.

## Changes

1. **`docs/adr/0013-revenue-inputs-and-margin.md`** — versioned run-rates,
   proration, conservative totals, coverage semantics, break-even, access.
2. **`plans/roles.md`** — endpoint rows for `project-rates` and `margin`
   (exec/admin only).
3. **`CONTEXT.md`** — glossary: *project rate*, *rate version*, *contribution*,
   *margin*, *coverage*, *break-even scale*.
4. **`.scratch/margin/`** — spec + tickets (this set).

## Acceptance

- ADR-0005's descope is explicitly amended, not contradicted silently.
- Every term the UI will show (coverage, break-even) has a definition.

## Result

- `docs/adr/0013-revenue-inputs-and-margin.md` records the reversal of
  ADR-0005's descope, the versioned run-rate model, conservative external
  totals, the internal-project exception, coverage semantics, break-even and
  exec-only access.
- `plans/roles.md` §6.2 gained the `project-rates`/`margin` row; `CONTEXT.md`
  gained *project rate*, *rate version*, *contribution*, *margin*, *internal
  project*, *coverage* and *break-even scale*; `docs/06` gained F53–F57.
