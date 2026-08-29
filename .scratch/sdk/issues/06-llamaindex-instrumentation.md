# LlamaIndex instrumentation scope

Type: grilling
Status: resolved
Blocked by: 01

## Question

Which LlamaIndex components must v1 tracing cover (LLM calls, indices, retrievers, query engines, agents, tools)? Do we reuse/extend existing OpenInference/OTel LlamaIndex instrumentation, or wrap custom? Where do LlamaIndex spans map onto our workflow/agent trace model?

## Answer

Decided by grilling with the user.

- **Reuse**: activate `openinference-instrumentation-llama-index` (v4.x, llama-index >= 0.12.x) with our TracerProvider; the SDK layers from tickets 02/04/09 (workflow boundaries, provider normalization, failure attributes, retry inference) apply unchanged. No custom tracing.
- **v1 coverage**: full component sweep — LLM calls, query engines/chains (CHAIN), retrievers (RETRIEVER with documents), embeddings (EMBEDDING), agents (AGENT via `AGENT_STEP`), tools (TOOL via `FUNCTION_CALL`), rerankers (RERANKER).
- **Version support**: current instrumentor matrix only (llama-index >= 0.12.x); legacy versions are best-effort, documented in the plan.
- **Trace-model mapping**: LlamaIndex spans nest under the manual workflow CHAIN root via context propagation — identical to LangChain, so a workflow can mix both frameworks under one root. AGENT spans come from the instrumentor's callback mapping; the SDK keeps the same small reclassification hook as LangChain (ticket 05) for misfired AGENT spans.
- **Streaming/async**: rely on the instrumentor's streaming paths (accumulated tokens, status on stream error); callbacks cover sync + async.
- **Double-instrumentation guard**: same init-time warning as LangChain if another LlamaIndex/provider instrumentor is active.