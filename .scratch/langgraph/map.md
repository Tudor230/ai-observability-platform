## Destination

First-class LangGraph support in the SDK (`sdk/`) with automatic human-in-the-loop (HITL) capture, thoroughly tested. The map is complete when the `_langgraph.py` auto-interception module, its unit tests, the mock-workflow scenarios, and the plan updates in `plans/` are all in place, with every decision below resolved.

## Notes

- Domain: AI observability / agentic monitoring. The SDK already reuses `openinference-instrumentation-langchain` (pyproject pin `>=0.1.73`; venv 0.1.74), which traces LangGraph because LangGraph is built on `langchain-core`.
- Skills: research for 01; grilling for 02; task for 03–05. Read `plans/sdk.md` before deciding; the SDK's decision index links to the `.scratch/sdk/` tickets.
- Settled before charting (user): auto-interception (boundary patch + lifecycle hook), no manual `hitl()` helper; `sdk.hitl.*` attributes stamped on the workflow root by the enrichment layer; LangGraph support must be thoroughly tested; keep interception logic in a new `_langgraph.py` with small hooks threaded into existing modules.
- Research baseline (verified against installed instrumentor 0.1.74 and LangGraph callbacks docs):
  - LangGraph node spans are `CHAIN`/`AGENT` with LangGraph `metadata.langgraph_node`/`langgraph_step`; `session.id` from LangChain thread/conversation metadata.
  - Since instrumentor `>=0.1.67`, `GraphInterrupt` is in `IGNORED_EXCEPTION_PATTERNS` → interrupted node spans get status `OK`, but a residual `GraphInterrupt` exception event can remain, which the SDK's `_errors.is_failed()` would otherwise misread as a failure.
  - The interrupt payload and resume value exist **only** in the runtime (`result["__interrupt__"]`, `Command(resume=...)`, `stream` marker chunks, `GraphCallbackHandler` events) — not in any span.
  - Phoenix has no dedicated HITL UI: an interrupted run is a normal OK trace ending at the interrupting node; resuming creates a separate trace; the two group under a Phoenix **session** when `session.id` (= our `workflow_id`) equals the LangGraph thread id. `sdk.hitl.*` attributes render in the span inspector. The Agent Graph/Path view is Arize AX (paid), driven by `metadata.langgraph_node`.

## Decisions so far

<!-- the index: one line per closed ticket, enough to judge relevance, then zoom the link for the detail the ticket holds -->

- [LangGraph instrumentation](issues/01-langgraph-instrumentation.md): reuse the LangChain instrumentor; LangGraph nodes trace as CHAIN/AGENT with `metadata.langgraph_node`; interrupts get OK status (instrumentor >= 0.1.67) but may leave a `GraphInterrupt` exception event; payload/resume values are not captured by any instrumentor.
- [LangGraph HITL capture](issues/02-langgraph-hitl-capture.md): auto-intercept at the graph boundary (wrapt patches on `Pregel.invoke/ainvoke/stream/astream`) plus a `GraphCallbackHandler` lifecycle hook (langgraph >= 1.1.9); `sdk.hitl.*` attribute scheme; a bounded trace-keyed registry in `_state`; the enrichment layer stamps the workflow root at export; control-flow exceptions (`GraphInterrupt`/`GraphBubbleUp`/`Command`/`ParentCommand`) are excluded from failure detection; logic lives in `_langgraph.py`, constants/filter/registry/wiring split into `_attributes.py`/`_errors.py`/`_state.py`/`_enrichment.py`/`_instrumentation.py`.
- [Unit tests](issues/03-langgraph-unit-tests.md): thorough `tests/unit/test_langgraph.py` covering interception helpers, registry behavior, boundary-patch mechanics (real langgraph), lifecycle hook, control-flow failure filtering, and enrichment HITL stamping; guard tests in `test_instrumentation.py`.
- [Mock scenarios](issues/04-langgraph-mock-scenarios.md): `langgraph>=1.1.9` dev dep; scenarios `lg_basic`, `lg_hitl_interrupt`, `lg_hitl_resume`, `lg_hitl_stream`; wire into `runner.py` + `mock_workflows/__init__.py`.
- [Assemble the plan](issues/05-assemble-langgraph-plan.md): update `plans/sdk.md` (scope, §7.1, new HITL section, §10, decision index) and `plans/implementation-plan.md` (deferred items).
- [Trace-id continuation](issues/06-trace-continuation.md): Langfuse-style deterministic trace id derived from `workflow_id` (= thread id) — no store; interrupt + resume join ONE trace via a synthetic remote parent; `HITLRegistry` keyed `(trace_id, root_span_id)`; enricher handles multi-root continued traces with per-root failure propagation.

## Not yet specified

- `sdk.hitl.node` best-effort capture (current-span name at `on_interrupt` time) — verify empirically in the scenario suite.
- Async streaming (`astream`) interrupt capture end-to-end beyond the unit test.
- LangGraph on langgraph < 1.1.9: boundary patch still captures invoke/stream interrupts; the lifecycle hook degrades silently.

## Out of scope

- Custom re-tracing of LangGraph nodes (the LangChain instrumentor owns node spans; a `register_span_kind_override` hook exists if AGENT reclassification is ever wanted).
- Phoenix/backend UI work and the Agent Graph/Path visualization (AX-only).
- The business agents being monitored.