# 05 — Frontend: Manager and Executive insight sections

Type: task
Status: in progress
Blocked by: 01, 03, 04
Area: phoenix insights, pages
Estimate: M

## Goal

Both role pages get the Phoenix-style chart sections, scoped to their role:
Manager is the operational view (reliability, usage, models & tools), Executive
the cost/trend view (traffic, model economics).

## Changes

1. **`pages/Manager.tsx`**
   - *Reliability*: executions over time (ok/failed), latency quantiles,
     error rate over time, failures by kind.
   - *Usage*: tokens by type (input vs output), cost per execution.
   - *Models & tools*: top models by cost, latency by model (avg/p95), tool
     calls and errors, slowest tools — the two entity panels carry their own
     `TableFilters` (`model_insights`, `tool_insights`).
   - Existing cost cards, budgets, alerts and trends stay.
2. **`pages/Executive.tsx`**
   - *Traffic & reliability* (grid-3): executions over time, latency quantiles,
     error rate over time.
   - *Usage economics*: tokens by type, cost per execution, failures by kind.
   - *Model economics* (grid-3): top models by cost, top models by tokens,
     latency by model.
   - Existing forecast, cost trend and the two cost cards stay.
3. **`api/types.ts` / `api/client.ts` / `api/hooks.ts`** — `ModelInsight` /
   `ToolInsight` types, `models` / `tools` api calls, `useModels` / `useTools`
   hooks with the card filters.
4. **Tests** — Manager/Executive: the new sections render their titles and
   charts from mocked hooks; the entity panels pass their namespaced filters.

## Acceptance

- Both pages render fixed-height chart cards; nothing scrolls.
- Entity panels filter independently through the URL (namespaced params).
- Empty windows show per-panel empty states, not blank cards.

## Tests

- `npm run test` (+ coverage gate), `npm run lint`, `npm run build`.
