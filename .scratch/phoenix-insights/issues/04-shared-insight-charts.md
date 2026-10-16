# 04 — Frontend: shared insight charts + Overview refactor

Type: task
Status: in progress
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
