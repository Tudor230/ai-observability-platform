# 01 — Frontend: per-1M unit costs + richer Executive/Manager stat rows

Type: task
Status: resolved
Area: phoenix insights, stat cards
Estimate: S

## Goal

Executive's stat row no longer shows "Cost per 1k tokens" / "Cost per successful
execution", and both Manager and Executive gain the stats the Phoenix project
header shows (latency, tokens, spend per execution, budget headroom).

## Changes

1. **`lib/format.ts`** — add `formatUnitCost`: 4 decimals (`$0.0294`), 6
   decimals below $0.0001, `—` for null/NaN. Used for unit costs only.
2. **`pages/Executive.tsx`** — six grid-3 cards: Total AI cost (delta), Cost per
   1M tokens (`totalCost / total_tokens * 1e6`), Cost per execution (unit cost),
   Executions (sub "N failed"), Total tokens (sub "in / out"), p95 latency (sub
   p50). Drop `costPer1kTokens`, `successful` and `costPerSuccess`.
3. **`pages/Manager.tsx`** — eight grid-4 cards: Total cost (delta), Executions
   (delta), Error rate (delta), Open alerts, p95 latency (sub p50), Cost per
   execution, Tokens (sub "in / out"), Budget utilization (worst case, sub
   "N budgets" / "no budgets").
4. **Tests** — Executive shows "Cost per 1M tokens" and no "Cost per successful
   execution"; Manager shows the new eight labels.

## Acceptance

- Per-1M values render with 4 decimals; totals keep `formatMoney`.
- Manager's budget card reflects `/budgets/status` (worst utilization) and
  degrades to "—" with no budgets.

## Tests

- `npm run test` (+ coverage gate), `npm run lint`, `npm run build`.

## Result

- `formatUnitCost` renders `$0.0294` (6 decimals below $0.0001), totals keep
  `formatMoney`.
- Executive: grid-3 ×2 — Total AI cost (delta), Cost per 1M tokens, Cost per
  execution, Executions (+ failed, delta), Total tokens (in/out), p95 latency
  (p50 sub). `costPer1kTokens` / `costPerSuccess` deleted.
- Manager: grid-4 ×2 — the four original cards plus p95 latency, cost per
  execution, tokens (in/out, summed from the same day-metric series the trend
  chart uses) and worst-case budget utilization.
- Evidence: 516 frontend tests pass (new "renders the eight-card operational
  stat row"; Executive asserts the 1M label and the absence of the 1k and
  success-only cards), lint + build clean, coverage 88.7/73.8/68.7.
