# 03 — Ollama tests

Type: task
Status: resolved
Blocked by: 02

## Goal

Cover the raw-client path offline — unit tests plus mock-workflow scenarios —
without a local Ollama server.

## Changes

1. `sdk/src/mock_workflows/ollama/fakes.py` — the real client and real
   instrumentor run; only the HTTP boundary (`Client._request`) is replaced:
   `chat_response()` (fixed usage), `stream_chunks()` (content fragments + a
   final chunk carrying model/usage), `MockRateLimitError`, and the
   `patched_ollama(...)` patch context manager.
2. `sdk/src/mock_workflows/ollama/scenarios.py` — `oll_chat` (provider/model/
   tokens/messages), `oll_chat_error` (rate_limit hint + root ERROR),
   `oll_chat_redacted` (capture off: messages stripped, tokens kept),
   `oll_chat_stream` (one span, accumulated output, final counts). Wired into
   `mock_workflows/__init__.py` and `runner.py`.
3. `sdk/tests/unit/test_ollama.py` — guard lifecycle, absent-client skip, chat
   span shape, error classification + root propagation, default redaction,
   streaming accumulation, and no span after `uninstrument()`.
4. `sdk/tests/unit/test_instrumentation.py` — guard assertions extended to
   Ollama (double-instrument detection, uninstrument clears).

## Comments

Implemented. `tests/scenarios/test_scenarios.py` picks the new scenarios up
automatically (parametrized over `SCENARIOS`).

Evidence: `uv run pytest` 139 passed + 1 skipped (was 128 + 1); new file adds
8 tests, 3 guard assertions added to the instrumentation tests.
