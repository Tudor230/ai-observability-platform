# OpenInference coverage research

Type: research
Status: resolved
Blocked by:

## Question

What do OpenInference semantic conventions and existing OpenTelemetry Python instrumentations already cover for AI observability (LLM calls, tools, retrieval, agents, errors, token usage), and what must our own SDK add? Map the gaps for LangChain and LlamaIndex specifically.

## Answer

Resolved by research subagent on branch `research/openinference-coverage`; full findings with sources: `.scratch/sdk/research/01-openinference-coverage.md`.

- OpenInference defines 10 span kinds (`LLM`, `EMBEDDING`, `CHAIN`, `RETRIEVER`, `RERANKER`, `TOOL`, `AGENT`, `GUARDRAIL`, `EVALUATOR`, `PROMPT`) via `openinference.span.kind`; conventions cover messages, model/provider, token counts (incl. cache/reasoning), tools, retrieval docs, session/user id, metadata.
- Cost attributes exist (`llm.cost.prompt/completion/total`) but there are **no error/failure/retry attributes** — only standard OTel `exception.*` + span status.
- `openinference-instrumentation-langchain` (v0.1.73) and `-llama-index` (v4.4.8) are stable; activated via `LangChainInstrumentor().instrument()` / `LlamaIndexInstrumentor().instrument(tracer_provider=...)`. Both capture prompts/messages by default, token usage, tool calls, retrievers, embeddings, AGENT/CHAIN kinds, and errors (status ERROR + record_exception). Neither emits cost, retries, or session/workflow boundaries.
- Phoenix ingests OTLP HTTP at `:6006/v1/traces`, stores spans as-is, computes token counts and cost server-side (token counts + pricing table; won't honor external span costs — issue #13655); it does NOT classify failures — that's the backend's job.
- SDK gaps to fill: workflow/agent outer span with session/user/agent attributes; business-context metadata; own namespaced failure/retry attributes (no convention exists); gating prompt capture (instrumentors capture by default) via config options; accurate token/model/provider for the cost engine (LangChain provider map misses several providers); own TracerProvider + BatchSpanProcessor + OTLP exporter with Resource (service.name/version, deployment.environment); avoid double-instrumenting provider SDKs (nested spans, streaming token undercount — issue #2268).