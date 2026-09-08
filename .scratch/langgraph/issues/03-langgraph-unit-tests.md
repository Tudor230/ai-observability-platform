# LangGraph unit tests

Type: task
Status: resolved
Blocked by: 02

## Question

What must be tested so LangGraph support (especially `_langgraph.py`) is thoroughly covered?

## Answer

Mirror the existing conventions (`tests/unit/test_*.py` with the `tail_exporter` fixture for full-pipeline assertions, and `tests/unit/helpers.py` `make_span`/`enrich`/`exception_event` for enrichment-layer-only assertions). Add `tests/unit/test_langgraph.py` and extend `tests/unit/test_instrumentation.py`:

- **Extraction helpers (pure, no langgraph):**
  - `__interrupt__` → `sdk.hitl.interrupt_payload` JSON; non-JSON-serializable payloads serialize via `default=str`.
  - `Command(resume=...)` input → `sdk.hitl.resume_value`; plain dict input → no resume value.
  - thread_id from `config["configurable"]["thread_id"]`; missing config / missing thread_id → `None`.
  - Result without `__interrupt__` → no payload; no attribute when nothing meaningful is captured.
- **Registry (`_state.HITLRegistry`):** trace-keyed `record`/`take`; first-writer-wins per key; `take` returns and removes; bounded size evicts oldest on overflow; empty `record` is a no-op.
- **Boundary patch (real langgraph graph):**
  - After `instrument_langgraph()`, `Pregel.invoke` is wrapped: an interrupting graph records payload + thread_id; a resumed graph records resume value.
  - `ainvoke` async path records the same.
  - `stream` (and `astream`) capture the interrupt marker chunk.
  - Pass-through: wrapper returns the original result unchanged and re-raises original exceptions.
  - `uninstrument_langgraph()` restores the original methods (identity check against a captured original).
  - `instrument_langgraph()` is idempotent (no double-wrap) and `_already_instrumented_langgraph()` flips correctly.
- **Lifecycle hook:** the SDK handler subclasses `GraphCallbackHandler`; `on_interrupt`/`on_resume` record into the registry; injection into `get_sync/async_graph_callback_manager_for_config` yields a manager whose handlers include the SDK handler; no crash when langgraph lacks `GraphCallbackHandler`.
- **Control-flow failure filtering (`_errors`):**
  - OK span with a `GraphInterrupt`/`GraphBubbleUp`/`Command`/`ParentCommand` exception event → not failed.
  - ERROR span whose only exception event is control-flow → not failed.
  - ERROR span with no events → failed; ERROR span with a real exception event → failed; OK span with a real exception event → failed.
  - Enrichment: node span with a `GraphInterrupt` event + OK status → no `sdk.error.*`, root stays OK; a real error alongside still propagates to the root.
- **Enrichment HITL stamping:** root receives pending `sdk.hitl.*` from the registry for its trace_id; existing root attributes are not overwritten; no registry entry → no `sdk.hitl.*`; the registry entry is consumed (removed) after the trace is processed.
- **Instrumentation guards (`test_instrumentation.py`):** `_already_instrumented_langgraph()` is True after `init()` and False after `uninstrument_frameworks()`.