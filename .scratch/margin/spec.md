# Margin — revenue inputs, margin and scaling forecast

Status: delivered (2026-10-16)
Source: product decision to reverse the margin descope (ADR-0005) and give the
exec view revenue, margin and a scaling/break-even forecast.
Convention: phase-ordered commits, one per ticket, on `feat/refinements`.

## Settled decisions (planning session, 2026-10-16)

1. **Margin = revenue − manual cost − AI cost.** Both revenue and manual cost
   come from explicit exec/admin inputs (ADR-0013); manual cost is optional and
   defaults to 0, flagged as unset.
2. **Rates are versioned run-rates.** Each version carries an explicit
   `effective_from`; the active rate for a day is the greatest
   `effective_from <= day`. Versions never overwrite each other, two versions
   may not share a date (409), and existing versions are editable/deletable.
3. **Revenue shape**: one revenue amount + period (`month`|`year`) and one
   manual-cost amount + period per version; USD only.
4. **Access**: reading margin and managing rates is exec/admin only (managers
   keep cost-only views). The admin key bypasses the role check as elsewhere.
5. **Totals are conservative**: all AI cost counts, including projects and days
   with no active rate. Coverage is reported beside the totals (projects with an
   active version, share of AI cost on covered days); rows without a rate show
   no margin rather than $0.
6. **Scaling forecast** is a volume multiplier (×1 ×2 ×5 ×10) plus the
   **break-even scale** = (revenue − manual cost) ÷ AI cost, with the
   forward-looking numbers taken from the version active on the last day of the
   window.
7. **Executive drops latency.** Both latency panels leave the exec page
   (Manager keeps them); the freed space is margin.
8. **`undefined executions` fix**: `/costs?dimension=model` grows `executions`
   (distinct) and `calls` (billed rows), so the Models card shows real numbers.
9. **Internal projects need no revenue.** Added mid-implementation: a project
   can be flagged *internal* (tooling, R&D, demos). Its AI cost is reported as
   *internal spend*, excluded from margin totals and coverage, and the flag wins
   over any rate versions — so internal work never reads as a loss.

## Tickets

| # | Phase | Scope |
|---|---|---|
| 01 | 0 | Docs: ADR-0013 (amends ADR-0005), `plans/roles.md` rows, `CONTEXT.md` glossary, spec + tickets |
| 02 | 1 | Backend: `project_rates` version table + migration + list/create/edit/delete |
| 03 | 1 | Backend: `GET /margin` — per-day version resolution, proration, margin, break-even, coverage, daily series |
| 04 | 1 | Backend: `/costs?dimension=model` gains `executions` + `calls` |
| 05 | 2 | Frontend: api types/hooks, project-rates versions dialog, Executive margin surface (stats, margin over time, margin by project, margin forecast, scaling) |
| 06 | 3 | Docs + verification (audit entries, suites, live pass as exec) |

## Design notes

- **Proration**: daily amount = `amount / period_days` with `month ≡ 365/12`,
  `year ≡ 365`; a window's revenue is the sum over its days of the day's active
  version. A mid-window price change therefore appears as a step.
- **Coverage** is computed from execution-day cost per project (the same source
  as the totals), so it is self-consistent: `covered_cost / total_cost`.
- **`/margin` row shape**: `project_id`, `name`, `rate` (active version or
  `null`), `covered_days`, `window_days`, `revenue`, `manual_cost`, `ai_cost`,
  `margin`, `margin_pct`, `executions`, `cost_per_execution`,
  `break_even_scale`, `break_even_executions`; plus `totals` (with coverage) and
  a daily `series` (`day`, `revenue`, `manual_cost`, `ai_cost`, `margin`).
- **Sorting**: worst margin first, then the projects without a rate by AI cost.
- **No pipeline change**: rates are configuration, read by the read API only.

## Verification

- Backend: `pytest` + `ruff` + `mypy`; new tests for version resolution, the
  409 clash, edit/delete, proration across a mid-window change, uncovered days,
  break-even guards and the model-row fix. Migration applies on the dev DB.
- Frontend: `vitest` + coverage gates, `lint`, `build`; new tests for the
  editor dialog, the margin stats/panels and the scaling maths.
- Live: `exec@local` on the rebuilt stack with two rate versions seeded, so the
  margin view shows a real step and a real break-even number.
