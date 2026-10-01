# 05 — Ollama pricing ($0 default)

Type: task
Status: resolved
Blocked by: 02

## Goal

Make local models show **$0.00** instead of "unpriced" (`NULL`) in the cost
engine, without weakening the "unpriced → NULL, never fabricated" rule
(`.scratch/backend/issues/03-cost-engine.md`).

## Changes

1. `backend/src/aiobs_backend/seed.py` — add
   `("ollama", "*", "default", 0.0, 0.0, None, None, None)` to
   `DEFAULT_PRICING`. Seeding is idempotent and runs at startup
   (`main.py` when `settings.seed_pricing`), in `scripts/kpi_gate.py`, and in
   `scripts/e2e_smoke.py`; existing deployments pick the row up on restart.
2. `backend/tests/conftest.py::_seed_pricing` — same provider-default row for
   ingest tests.
3. `backend/tests/test_pricing.py` — new
   `test_local_model_cost_is_zero_via_provider_default`: an `ollama` LLM span
   (`granite4.2:3b`, 1234/567 tokens) prices at exactly `0.0` on the span, the
   execution, and the ingest response; the existing unpriced test (unknown
   provider → `NULL`) stays as the control.

## Acceptance

- A local-model execution reports `total_cost = 0.0` (not `None`).
- An unknown provider still reports `NULL` (unpriced) — the rule is unchanged;
  operators can delete the row via the pricing API to return to unpriced.
- `plans/backend.md` §8.1 documents the explicit zero-rate default.

## Comments

Implemented. Ollama chat spans carry no cache tokens, so the zero-rate row needs
no cache prices (`compute_llm_cost` returns `None` only when cache tokens exist
without a cache rate). `granite4.2:3b` resolves via the `default` match; no
exact row required.

Evidence: `backend/tests/test_pricing.py` 4 passed (including the new test).
