# 04 — Backend: model cost rows carry executions and calls

Type: bug
Status: resolved
Area: margin, costs API
Estimate: S

## Goal

The Executive Models card renders `${m.executions} executions`, but
`/costs?dimension=model` rows come from billing `cost_records` and never had an
`executions` field — the card showed "undefined executions".

## Changes

1. **`api/routes/costs.py`** — the model branch counts distinct executions and
   billed calls per provider·model and returns them with the cost/token fields.
2. **Tests** — extend the cost-row test to assert `executions` and `calls`.

## Acceptance

- Model rows expose real execution and call counts; the card's sublabel is a
  fact.

## Tests

- `uv run pytest`.

## Result

- The `/costs?dimension=model` branch counts distinct executions and billed
  calls and returns `executions`, `calls`, `total_tokens` and the `tokens`
  alias with the cost/token fields.
- Evidence: `tests/test_ingest.py::test_model_cost_rows_carry_executions_and_calls`.
