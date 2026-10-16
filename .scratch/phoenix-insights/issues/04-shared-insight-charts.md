# 04 — Frontend: shared insight charts + Overview refactor

Type: task
Status: resolved
Blocked by: 03
Area: phoenix insights, charts
Estimate: M

## Goal

One implementation of every time-series and entity chart, composed by Overview,
Manager and Executive — chart JSX must not be copy-pasted between pages.

## Changes

1. **`lib/insightSeries.ts`** — pure mappers from the API shapes to chart rows:
   `dayMetricsToSeries` (cost, ok/failed, input/output, p50/p95/p99, error rate,
   executions, cost per execution), `failureRows` (failures by kind, stacked),
   `modelRows` / `toolRows` for the entity panels.
2. **`components/charts/insights.tsx`** — one component per panel, each a
   `CardPanel` with a fixed chart height and loading/empty handling:
   `TrafficChart`, `TokensChart`, `LatencyChart`, `ErrorRateChart`,
   `CostChart`, `CostPerExecutionChart`, `FailuresByKindChart`,
   `ModelsByCostChart`, `ModelsByTokensChart`, `ModelLatencyChart`,
   `ToolCallsChart`, `ToolLatencyChart`. Entity panels accept a `filters` slot
   (the per-card `TableFilters` control) and a `days` window.
3. **`pages/Overview.tsx`** — refactored onto the shared components with no
   visual change (cost, traffic, tokens, latency, failures by kind, error rate).
4. **Tests** — `charts.test.tsx` additions for the series mappers and the new
   panels; Overview keeps its existing assertions green.

## Acceptance

- Overview renders exactly the same six charts through the shared components.
- Every shared panel renders a skeleton while loading and an empty state with
  no data.
- `insightSeries` mappers are unit-tested (stacked keys, percentiles, cost per
  execution guard for zero executions).

## Tests

- `npm run test` (+ coverage gate), `npm run lint`, `npm run build`.

## Result

- `lib/insightSeries.ts`: `dayMetricsToSeries` (plus derived `ok`/`failed` and
  `cost_per_execution`), `failureRows` (day × kind pivot), `modelRows`,
  `toolRows` and `topBy`. Rows are `type` aliases so they stay assignable to
  `TrendChart`'s `Record<string, unknown>[]`.
- `components/charts/insights.tsx`: twelve panels — cost, cost/execution,
  traffic, tokens, latency, error rate, LLM & tool calls, failures by kind,
  top models by cost, top models by tokens, latency by model, tool calls and
  errors, slowest tools — each a fixed-height `CardPanel` with skeleton and
  empty states, and an optional `filters` slot in the header.
- Overview now composes those panels; its local `series` projection and
  failure pivot are gone.
- Evidence: 525 frontend tests (37 files) incl. 9 new `insightSeries` mapper
  tests; lint + build clean; coverage 89.5/74.7/70.7.
