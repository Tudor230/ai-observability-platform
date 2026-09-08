# LangGraph instrumentation

Type: research
Status: resolved
Blocked by:

## Question

How does LangGraph get traced today, and what is captured vs. missing for human-in-the-loop? Reuse the LangChain instrumentor or write custom LangGraph tracing?

## Answer

Researched against the installed `openinference-instrumentation-langchain` 0.1.74 (`sdk/.venv`) and the LangGraph callback docs.

- **Reuse the LangChain instrumentor — no custom node tracing.** LangGraph is built on `langchain-core`, so `LangChainInstrumentor` (already activated by the SDK in `_instrumentation.py`) traces every graph invocation: the graph run is a `CHAIN` span and each node run is a `CHAIN` span (or `AGENT` when the node name contains "agent"), with LangGraph's `metadata.langgraph_node` / `metadata.langgraph_step` / `checkpoint_id` carried in the span's `metadata` JSON attribute (`_tracer._metadata`, line 1452). LLM/TOOL spans from nodes nest beneath the node spans; everything nests under the SDK's manual `workflow()` CHAIN root via OTel context.
- **`GraphInterrupt` is already de-flagged by the instrumentor.** `IGNORED_EXCEPTION_PATTERNS` in `_tracer.py` includes `^GraphInterrupt\(` (plus `^Command\(`, `^ParentCommand\(`) since 0.1.67; `_update_span` forces the span status to `OK` when the run error matches. The `on_interrupt`/`on_resume` lifecycle callbacks are no-ops (lines 243–256). **However** the instrumentor still records the escaping `GraphInterrupt` as a span `exception` event before forcing OK — and our SDK's `_errors.is_failed()` treats *any* exception event as a failure, so the enrichment layer would wrongly stamp `sdk.error.*` and propagate `ERROR` to the workflow root. This is the SDK-side blocker this effort must fix.
- **Missing from any instrumentor:** the interrupt payload (the value passed to `interrupt()`, e.g. the question shown to a human) and the resume value (from `Command(resume=...)`). These exist only in the LangGraph runtime — `result["__interrupt__"]` (invoke/ainvoke), stream marker chunks `{"__interrupt__": ...}`, and `langgraph.callbacks.GraphCallbackHandler.on_interrupt(GraphInterruptEvent)` / `on_resume(GraphResumeEvent)` (langgraph >= 1.1.9). Capturing them is the SDK's job (ticket 02).
- **How Phoenix displays them** (confirmed via arize.com docs + phoenix discussions #5542/#13677): an interrupted run is a normal trace ending at the interrupting node with status OK; resuming is a *separate trace*; the two group under a Phoenix **session** only when `session.id` (= our `workflow_id`) equals the LangGraph thread id. There is no dedicated HITL UI; interrupt payloads are invisible unless the SDK emits them as span attributes. Agent Graph/Path visualization is Arize AX (paid), driven by `metadata.langgraph_node`.
- **Double-instrumentation guard:** no third-party LangGraph OpenInference instrumentor is standard (the LangChain instrumentor is the canonical one), so the guard is "already patched by us" + a warning when a LangGraph `Pregel` method is already wrapped.