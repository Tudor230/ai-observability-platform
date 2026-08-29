# LangChain instrumentation scope

Type: grilling
Status: resolved
Blocked by: 01

## Question

Which LangChain components must v1 tracing cover (LLM calls, chains, agents, tools, retrievers, memory)? Do we reuse/extend existing OpenInference/OTel LangChain instrumentation, or wrap custom? Where do LangChain spans map onto our workflow/agent trace model?

## Answer

Decided by grilling with the user.

- **Reuse**: activate `openinference-instrumentation-langchain` (v0.1.73+) with our TracerProvider; the SDK layers workflow boundaries, provider normalization, failure attributes, and retry inference (tickets 02/04/09) on top. No custom tracing.
- **v1 coverage**: LLM calls (prompts, tokens, finish reasons), agents (AGENT spans via the instrumentor's run-name heuristic), tools (TOOL spans), retrievers (RETRIEVER spans with documents), prompt templates. **Memory and rerankers are not covered** — the instrumentor doesn't trace memory, and LangChain reranker runs surface only as plain CHAIN spans (no RERANKER run_type mapping), so rerankers are deferred rather than reclassified in v1.
- **LangGraph: out of v1 scope.** Only LangChain Classic + 1.x (langchain_core hooks, incl. partner packages). LangGraph graphs trace only as far as the instrumentor reaches today (partial CHAIN coverage, interrupt/resume unhandled) — documented limitation in the plan.
- **Trace-model mapping**: framework spans nest under the manual workflow CHAIN root via context propagation (no extra work). AGENT detection = the instrumentor's heuristic; the SDK keeps a small documented reclassification hook for spans the heuristic misfires on.
- **Double-instrumentation guard**: SDK warns at init if another LangChain/provider instrumentor is already active (issue #2268 risk).
- **Streaming**: rely on the instrumentor's streaming paths (token accumulation, status on stream error); sync + async covered.