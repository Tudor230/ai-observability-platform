# 02 — Groq wiring & tests

Type: task
Status: resolved
Blocked by: 01

## Goal

Wire the Groq instrumentor into the SDK's framework instrumentation and keep
it consistent with the existing guards, teardown, and offline test approach.

## Changes

1. `sdk/pyproject.toml`
   - `dependencies`: `openinference-instrumentation-groq>=0.1.30`.
   - dev group: `groq>=0.9.0` (tests/scenarios only).
2. `sdk/src/ai_observability/_instrumentation.py`
   - `_groq_instrumentor` global; `instrument_frameworks()` calls
     `_instrument_groq(provider)`; `uninstrument_frameworks()` uninstruments
     and clears it (never raising).
   - `_groq_available()` — `importlib.util.find_spec("groq")`; absent → debug
     log and return.
   - `_already_instrumented_groq()` — wrapt proxy check on
     `groq.resources.chat.completions.Completions.create`; warns and skips on
     conflict.
3. `sdk/src/mock_workflows/groq/`
   - `fakes.py`: scripted `httpx.MockTransport` responses injected through
     `Groq(http_client=...)`; `chat_completion(...)` and
     `rate_limit_response()` fixtures; no API key, no network.
   - `scenarios.py`: `groq_chat`, `groq_chat_error`, `groq_redacted` (workflow
     root `rca`, the motivating app's shape).
4. `sdk/tests/unit/test_groq.py` + guard coverage in
   `test_instrumentation.py`.

## Acceptance

- `init()` instruments the raw client; the guard is `True` after init and
  `False` after `uninstrument_frameworks()`.
- `init()` without `groq` installed skips silently; instrumentor failures never
  escape `init()`.
- Scenarios pass offline through the real client + instrumentor.

## Comments

Implemented. Full runs: `uv run pytest` 160 passed + 1 skipped (28 collected
scenarios included); `uv run aiobs-mock` 28/28 scenarios; backend suite 110
passed (incl. the seeded-rate pricing test). Live smoke against the running
platform backend: `groq_chat` → `Completions` LLM span with provider/model and
tokens 11/7 priced at $0.000006 from the seeded $0.15/$0.60 rate;
`groq_chat_error` → ERROR span with `rate_limit` hint; `groq_redacted` →
tokens only.
