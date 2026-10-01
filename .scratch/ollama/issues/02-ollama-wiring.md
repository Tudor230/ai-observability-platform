# 02 — Ollama wiring

Type: task
Status: resolved
Blocked by: 01

## Goal

Wire the Ollama instrumentor into the SDK's framework instrumentation and keep
it consistent with the existing guards and teardown.

## Changes

1. `sdk/pyproject.toml`
   - `dependencies`: `openinference-instrumentation-ollama>=0.1.9`.
   - `[dependency-groups] dev`: `ollama>=0.4.0` (tests/scenarios only).
2. `sdk/src/ai_observability/_instrumentation.py`
   - `_ollama_instrumentor` global; `instrument_frameworks()` calls
     `_instrument_ollama(provider)`; `uninstrument_frameworks()` uninstruments
     and clears it (never raising).
   - `_ollama_available()` — `importlib.util.find_spec("ollama")`; absent →
     `debug` log and return (no warning: most apps don't have it).
   - `_already_instrumented_ollama()` — wrapt proxy check on
     `ollama._client.Client.chat` (the symbol `wrap_function_wrapper` patches),
     mirroring `_already_instrumented_langchain`; warns and skips on conflict.
   - `instrument()` wrapped so an unexpected failure logs a warning and leaves
     `_ollama_instrumentor` unset (plan §8: instrumentation never breaks init).
3. No changes to `_enrichment.py` / `_usage.py` / `_errors.py` — LLM-kind
   enrichment is instrumentor-agnostic and `llm.provider=ollama` is never
   overwritten by provider normalization.

## Acceptance

- `init()` instruments the raw client; `_already_instrumented_ollama()` is
  `True` after init and `False` after `uninstrument_frameworks()`.
- `init()` without `ollama` installed skips silently.
- Instrumentor errors never propagate out of `init()`.

## Comments

Implemented. One subtlety found during implementation: `ollama._client` on the
package object is the module-level `Client` **instance**, which shadows the
submodule — the guard imports `from ollama._client import Client` instead of
using attribute access. `uv lock` bumped
`openinference-semantic-conventions` 0.1.35 → 0.1.39 (transitive).

Follow-up (same branch): the wiring was **unified** across all three
instrumentors after review — `_module_available` + `_langchain_available` /
`_llamaindex_available` / `_ollama_available` for the debug-level skip, and
`_safe_instrument()` for the never-propagate guarantee, applied to LangChain
and LlamaIndex too (previously they relied on OTel's ERROR-level
`DependencyConflict` path and let `instrument()` exceptions escape `init()`).

Evidence: `uv run pytest` 141 passed + 1 skipped; `uv run aiobs-mock` 22/22.
