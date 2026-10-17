# 05 — Frontend: rates dialog + Executive margin surface

Type: task
Status: resolved
Blocked by: 03, 04
Area: margin, dashboard
Estimate: M

## Goal

An exec opens the Executive page and sees revenue, margin, margin trend,
margin per project and a scaling/break-even scenario — and can maintain the
rates that drive it all from the same page.

## Changes

1. **api** — `ProjectRate`/`MarginRow`/`MarginResponse` types, `api.projectRates`
   (list/create/update/remove) and `api.margin`, `useProjectRates`/`useMargin`.
2. **`components/ProjectRatesDialog.tsx`** — project picker, version list
   (`effective_from · revenue /period · manual cost /period`) with add/edit/
   delete, inline validation and the `409` clash message; exec/admin only.
3. **`components/charts/insights.tsx`** — `MarginChart` (revenue and manual-cost
   accrual vs AI cost with a margin line) reused by the page.
4. **`pages/Executive.tsx`**
   - stats row → 8 cards: Total AI cost, Revenue, Margin, Margin %, Cost per 1M
     tokens, Cost per execution, Executions, Total tokens;
   - **latency panels removed** (Manager keeps them);
   - margin over time, margin by project (two-view `CostCard`, sortable, own
     filter namespace), margin forecast (linear cost forecast vs fixed revenue),
     scaling panel (×1 ×2 ×5 ×10 with cost/margin and the break-even callout);
   - coverage chip ("N of M projects have a rate · X% of cost covered") and an
     empty state with an "Add project rates" action when no rate exists.
5. **Tests** — dialog add/edit/delete + clash; stats labels; margin panels
   render from mocks; scaling maths (×2 halves the margin, break-even text);
   the no-rate empty state.

## Acceptance

- No rate book → the margin panels show the action empty state, never `$0`
  revenue or a fabricated loss.
- Partial coverage is visible next to the totals.

## Tests

- `npm run test` (+ coverage gate), `npm run lint`, `npm run build`.

## Result

- api: `ProjectRateVersion`/`ProjectRatesEntry`/`MarginRow`/`MarginTotals`/
  `MarginResponse` types, `api.margin`, `api.projectRates`
  (list/create/update/remove/setInternal), `useMargin`, `useProjectRates`.
- `components/ProjectRatesDialog.tsx`: project picker, version list with
  edit/delete, add/edit form, inline `409` clash message, internal toggle.
- `components/MarginScaling.tsx`: ×1/×2/×5/×10 projection of AI cost and margin
  plus the break-even callout.
- `components/charts/insights.tsx`: shared `MarginChart`.
- Executive: 8 stat cards (Total AI cost, Revenue, Margin, Margin %, Cost per
  1M tokens, Cost per execution, Executions, Total tokens), the coverage line,
  margin over time + scaling, the sortable margin-by-project `CostCard`
  (project-only filter), the rates editor button, the no-rates empty state with
  an action, and both latency panels removed.
- `TableFilters` gained a `fields` prop so a card only offers what its endpoint
  supports.
- Evidence: 529 frontend tests (new: the 8-card row, latency absence, coverage
  line, the no-rates CTA, the scaling maths at ×2/×10, the versions dialog
  incl. the 409 message, and the internal toggle).
