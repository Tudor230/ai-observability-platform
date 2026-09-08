# LangGraph HITL auto-capture

Type: grilling
Status: resolved
Blocked by: 01

## Question

How should the SDK automatically capture the interrupt payload and resume value so the human-in-the-loop parts are viewable, without a manual `hitl()` helper? What attributes, where do they live, and how do they reach the workflow root?

## Answer

Decided by grilling with the user: **fully automatic interception** — no manual `hitl()` helper.

- **New module `_langgraph.py`** (kept separate: it is custom framework instrumentation — wrapt-patching `Pregel` methods and a `GraphCallbackHandler` subclass — unlike the existing single-concern helper modules). Small hooks thread into existing modules where they genuinely belong:
  - `_attributes.py` — `sdk.hitl.*` constant names (not payload attributes; always captured, independent of `capture_prompts`).
  - `_errors.py` — control-flow exception filtering in `is_failed()`.
  - `_state.py` — the bounded, lock-guarded `HITLRegistry` (trace-keyed, first-writer-wins, overflow-evicts-oldest).
  - `_enrichment.py` — stamp pending `sdk.hitl.*` on the workflow root at export (and it owns `sdk.error.*` avoidance implicitly via `is_failed`).
  - `_instrumentation.py` — only the `instrument_langgraph()` / `uninstrument_langgraph()` calls + guard.
- **Boundary patch (both directions, any langgraph version):** wrapt-wrap `Pregel.invoke` / `ainvoke` / `stream` / `astream`:
  - Resume value: the input is `Command(resume=...)` → `sdk.hitl.resume_value` (JSON) + `sdk.hitl.interrupted="false"`.
  - Interrupt payload: the result dict (invoke) or stream marker chunk carries `__interrupt__` (tuple of `Interrupt` with `.value`) → `sdk.hitl.interrupt_payload` (JSON) + `sdk.hitl.interrupted="true"`.
  - Thread id: `config["configurable"]["thread_id"]` → `sdk.hitl.thread_id` (recorded only alongside an interrupt/resume to avoid noise on plain runs).
  - The wrapper is a pass-through: returns/raises exactly what the original does; failures never break the app.
- **Lifecycle hook (typed source, langgraph >= 1.1.9):** patch `get_sync_graph_callback_manager_for_config` / `get_async_graph_callback_manager_for_config` to inject an SDK `GraphCallbackHandler`. `on_interrupt(GraphInterruptEvent)` captures `event.interrupts` payloads (+ best-effort `sdk.hitl.node` from the current span name); `on_resume(GraphResumeEvent)` captures `checkpoint_id`. Degrades silently on older langgraph (the boundary patch still covers invoke/stream).
- **Delivery path:** capture writes into `state.hitl` keyed by the current OTel `trace_id` (valid whenever a span is active); the enrichment layer consumes `state.hitl.take(trace_id)` when the workflow root is processed and merges into root attributes without overwriting existing values. First-writer-wins dedups the boundary patch vs. the lifecycle hook.
- **Failure semantics:** interrupted workflows must NOT be failures. `is_failed()` ignores exception events whose `exception.type` is a control-flow type (`GraphInterrupt`, `GraphBubbleUp`, `Command`, `ParentCommand`); an `ERROR` span whose only exception event is control-flow is not failed; real exceptions still are. The workflow root therefore stays `OK` for a paused-for-approval run, with no `sdk.error.*`.
- **No public API change** (`init()`/`workflow()`/`span()`/`flush()`/`shutdown()` unchanged).
- **Phoenix correlation guidance:** set `workflow(workflow_id=thread_id)` so `session.id` groups the interrupt and resume traces into one Phoenix session.