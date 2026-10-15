# 04 — Backend: rich `/costs` rows for cost detail views

Type: task
Status: open
Blocked by: 03
Area: refinements v3, table UX (detail views)
Estimate: S

## Goal

Give the two-view cost cards their detail data without new endpoints: the
`/clients` row shape (executions, failures, error rate, cost, tokens, avg
duration, last seen) moves onto `/costs` rows.

## Changes

1. **`api/routes/costs.py`** — the `exec_aggregates` branch of `/costs` adds
   `failed_executions`, `error_rate`, `avg_duration_ms`, `last_seen` and
   `total_tokens` per bucket, keeping `tokens` (existing breakdown consumers)
   and the existing sort by `total_cost` desc.
   - The historical/`CostRecord` branch keeps its current shape; document the
     difference in the route docstring.
   - Cost stays stripped for client-only callers (`cost_visible`), as today.
2. **Tests** — extend `tests/test_cost_history.py` (or `test_costs.py`) to
   assert the new fields, including `error_rate` matching
   `failed_executions / executions` and `total_tokens == tokens` on the same
   rows.

## Acceptance

- `GET /api/v1/costs?dimension=project|workflow|team|model` returns rows with
  `executions`, `failed_executions`, `error_rate`, `total_cost`, `tokens`,
  `total_tokens`, `avg_duration_ms`, `last_seen` (nulls tolerated).
- Client-only callers still receive no `total_cost`.

## Tests

- `uv run pytest -q`, `ruff`, `mypy`.
