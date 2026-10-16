# Phoenix insights — model/tool insights, richer stats, chart parity

Status: delivered (2026-10-16)
Source: follow-up on refinements v3 — dashboard parity with the Arize Phoenix
project dashboards (more stat cards, more graphs, model/tool insights) plus the
cost-card table overflow review.
Convention: phase-ordered commits, one per ticket, on `feat/refinements`.

## Settled decisions (planning session, 2026-10-16)

1. **Executive stat row**: "Cost per successful execution" is dropped and "Cost
   per 1k tokens" becomes **cost per 1M tokens** — pricing is per-1M everywhere
   else in the product (`pricing.input_price_per_1m`, the Pricing page). The row
   becomes six grid-3 cards, adding p95 latency and keeping executions/tokens.
2. **Manager stat row grows to eight** (grid-4 ×2): total cost, executions,
   error rate, open alerts, p95 latency, cost per execution, tokens, budget
   utilization. Deltas come from `/overview`.
3. **Unit costs get their own formatter** (`formatUnitCost`, 4 decimals):
   `formatMoney` rounds to cents above $0.01, which would render a per-1M value
   of $0.0294 as "$0.03". Totals keep `formatMoney`.
4. **Chart parity is served by one shared module.** The time-series charts that
   already exist on Overview (traffic ok/failed, tokens in/out, latency
   quantiles, error rate, failures by kind, cost) move into
   `components/charts/insights.tsx` + `lib/insightSeries.ts` and are composed by
   Overview, Manager and Executive. No chart JSX is copy-pasted between pages.
5. **Two new read endpoints close the Phoenix gap we cannot serve today**:
   - `GET /models` — per provider·model: calls, failed calls, error rate,
     latency (avg/p95), cost and tokens (from the billing `cost_records`).
   - `GET /tools` — per tool: calls, failed calls, error rate, latency
     (avg/p95), executions, last seen.
   No schema change: `spans.llm_provider/llm_model/tool_name/duration_ms/status`
   and `cost_records` already carry every field.
6. **Out of scope** (data-model gaps, revisit later): sessions aggregation,
   hourly throughput rollup, cost split by token type, evals/annotations,
   prompt insights, embedding drift.
7. **Cost-card detail tables cannot overflow to the right**: `table-layout:
   fixed`, a fixed 40% label column that ellipsises, fixed numeric columns with
   `nowrap`, and the full label revealed on hover via a native `title`.
   Scoped to `.table-wrap--capped` — Engineering and the other tables are
   unchanged.

## Tickets

| # | Phase | Scope |
|---|---|---|
| 01 | 1 | Frontend: 1M unit costs + Executive/Manager stat rows (`formatUnitCost`) |
| 02 | 1 | Frontend: cost-card detail tables — fixed columns, ellipsis, hover title |
| 03 | 2 | Backend: `GET /models` + `GET /tools` insights endpoints |
| 04 | 3 | Frontend: shared insight charts + Overview refactor |
| 05 | 3 | Frontend: Manager and Executive insight sections |
| 06 | 4 | Docs + verification gate (docs/06 audit, CONTEXT.md glossary, live pass) |

## Design notes

- **`/models` row shape**: `key` (`provider:model`), `provider`, `model`,
  `calls`, `executions`, `failed_calls`, `error_rate`, `total_cost` (stripped
  for client callers), `input_tokens`, `output_tokens`, `total_tokens`,
  `avg_duration_ms`, `p95_duration_ms`, `last_seen`. Cost/tokens come from
  `cost_records` (billing snapshot, survives pricing edits); calls/errors/
  latency come from LLM spans. Rows sort by cost (fallback: calls) descending.
- **`/tools` row shape**: `name`, `calls`, `executions`, `failed_calls`,
  `error_rate`, `avg_duration_ms`, `p95_duration_ms`, `last_seen`, sorted by
  calls descending. Tool name is `spans.tool_name` with a `spans.name`
  fallback.
- Both endpoints mirror `/agents`: `require_access("engineer", "manager",
  "client")`, `resolve_project_filter` scoping, `project_id`/`workflow`
  filters, `parse_dt`/`default_range` windows. Percentiles use
  `stats.percentile` over the window's span durations.
- **Chart placement**: Manager gets *Reliability* (traffic, latency quantiles,
  error rate, failures by kind), *Usage* (tokens by type, cost per execution)
  and *Models & tools* (top models by cost, latency by model, tool calls and
  errors, slowest tools). Executive gets *Traffic & reliability* (grid-3) and
  *Model economics* (grid-3) plus tokens/cost-per-execution/failures.
- **Filters**: time-series charts follow the page `days` window like Overview;
  the entity panels get their own namespaced `TableFilters`
  (`model_insights`, `tool_insights`) since they are per-entity aggregates.
- **Nothing scrolls**: chart bodies keep fixed heights (200–240px); the cost
  cards keep their 360px/6-row contract from refinements v3.

## Verification

- Backend: `pytest` + `ruff` + `mypy`; new route tests for aggregation,
  project scoping and client cost stripping.
- Frontend: `vitest` + coverage gates, `lint`, `build`; new tests per stat row
  and chart panel; the cost-card tests keep asserting 6 rows/page + sorting.
- Live: manager account plus a new `exec@local` login (Executive is exec-only)
  against the rebuilt compose stack.
