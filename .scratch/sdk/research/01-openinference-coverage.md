# OpenInference Coverage Research — Findings

Research ticket: `.scratch/sdk/issues/01-openinference-coverage.md`
Date: 2026-08-29
Scope: OpenInference semantic conventions, existing OpenTelemetry Python instrumentations (LangChain / LlamaIndex), Phoenix ingestion behavior, and gaps our SDK must fill.

---

## 1. OpenInference semantic conventions

### 1.1 Where they live

- Spec repo: https://github.com/Arize-ai/openinference — Apache-2.0, ~1,180 stars, ~300 forks (checked 2026-08-29).
- Spec files (markdown in `spec/`):
  - https://github.com/Arize-ai/openinference/blob/main/spec/semantic_conventions.md
  - https://github.com/Arize-ai/openinference/blob/main/spec/traces.md
  - https://github.com/Arize-ai/openinference/blob/main/spec/annotations.md
  - https://github.com/Arize-ai/openinference/blob/main/spec/configuration.md
- Rendered docs: https://arize-ai.github.io/openinference/ and https://arize-ai.github.io/openinference/spec/semantic_conventions.html
- Python constants: `openinference-semantic-conventions` package (`openinference/semconv/trace/__init__.py`), e.g. `SpanAttributes`, `MessageAttributes`, `ToolCallAttributes`, `OpenInferenceSpanKindValues`, `OpenInferenceLLMProviderValues`.
- Relation to OTel GenAI semconv: OpenInference is a separate, richer-for-payloads convention set; OTel GenAI conventions (`gen_ai.*`) are still experimental (Development status, `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`). No official mapping/migration between the two (openinference issue #2130). Our SDK should emit OpenInference since the backend is Phoenix.

### 1.2 Span kinds (`openinference.span.kind`, required on every span)

`OpenInferenceSpanKindValues` enum in `python/openinference-semantic-conventions`:

| Value | Meaning |
|---|---|
| `LLM` | One LLM call (chat/completion) |
| `EMBEDDING` | Embedding-model call |
| `CHAIN` | Link/glue step between LLM steps (router, postprocessor, planner) |
| `RETRIEVER` | Vector search / document lookup |
| `RERANKER` | Document reranking |
| `TOOL` | Tool/function invocation by an LLM or agent |
| `AGENT` | Reasoning block encompassing LLM+tool calls |
| `GUARDRAIL` | Input/output moderation |
| `EVALUATOR` | Evaluation of model outputs |
| `PROMPT` | Prompt-template rendering |
| `UNKNOWN` | (also present in the Python enum) |

### 1.3 Key attributes (flat keys; lists are flattened with indexed prefixes)

Identity / context:
- `openinference.span.kind` (required), `session.id`, `user.id`, `metadata` (JSON string), `tag.tags`, `agent.name`
- Inputs/outputs: `input.value`, `input.mime_type`, `output.value`, `output.mime_type` (on any span kind)

LLM span attributes:
- `llm.model_name`, `llm.provider` (openai, azure, anthropic, google, aws, xai, deepseek, groq, fireworks, moonshot…), `llm.system` (openai, anthropic, cohere, mistralai, vertexai…)
- `llm.input_messages.<i>.message.role/content`, `llm.output_messages.<i>.message.role/content`
- `llm.prompts.<i>.prompt.text`, `llm.choices.<i>.completion.text` (legacy completions API)
- `llm.invocation_parameters` (JSON), `llm.finish_reason`, `llm.prompt_template.template/.variables/.version`
- `llm.tools.<i>.tool.json_schema`
- Token usage: `llm.token_count.prompt`, `llm.token_count.completion`, `llm.token_count.total`, plus details: `llm.token_count.prompt_details.cache_read/cache_write/audio`, `llm.token_count.completion_details.reasoning/audio`
- Message/tool-call payloads: `message.role/content/name/tool_call_id`, `message.tool_calls.<i>.tool_call.id/.function.name/.function.arguments`, `message.function_call_name/.function_call_arguments_json`, multimodal `message.contents.<i>.message_content.*`

Tool span attributes: `tool.name`, `tool.description`, `tool.parameters` (JSON), `tool.json_schema`, `tool.id`
Retriever span attributes: `retrieval.documents.<i>.document.content/.id/.score/.metadata`
Reranker attributes: `reranker.query/.model_name/.top_k/.input_documents/.output_documents`
Embedding attributes: `embedding.model_name`, `embedding.invocation_parameters`, `embedding.embeddings.<i>.embedding.vector/.text`
Document attributes: `document.content/.id/.metadata/.score`

### 1.4 Cost and error/failure attributes defined in the conventions

Cost — **defined in the spec** (`llm.cost.*`, USD floats):
- `llm.cost.prompt`, `llm.cost.completion`, `llm.cost.total`
- `llm.cost.prompt_details.input/.cache_read/.cache_write/.cache_input/.audio`
- `llm.cost.completion_details.output/.reasoning/.audio`

Error/failure — **NOT defined in OpenInference conventions**:
- No `error.*` or `failure.*` or `retry` attributes exist in the spec.
- Only the standard OTel exception semantics apply: `exception.type`, `exception.message`, `exception.stacktrace`, `exception.escaped` (span events + span status `OK`/`ERROR`/`UNSET`).
- There is no span-kind-agnostic "outcome/failure type" attribute and no retry-count convention.

Conclusion: conventions cover payloads, identity, and token usage fully; cost is optional-but-specified; failure/retry metadata must come from the SDK (or be derived by the backend from exceptions/status).

---

## 2. Existing OTel Python instrumentations

### 2.1 Registry landscape

OpenTelemetry registry (https://opentelemetry.io/ecosystem/registry/) — Python LLM/AI instrumentation entries include:

- OpenInference instrumentors (Arize): `openinference-instrumentation-langchain`, `openinference-instrumentation-llama-index`, `openinference-instrumentation-openai`, etc. — the canonical OpenInference emitters.
- Official OTel GenAI instrumentors (experimental): `opentelemetry-instrumentation-genai-openai`, `genai-anthropic`, `genai-langchain` in `github.com/open-telemetry/opentelemetry-python-genai` — emit `gen_ai.*`, not OpenInference.
- Traceloop OpenLLMetry: `opentelemetry-instrumentation-langchain`, `opentelemetry-instrumentation-llamaindex` — in maintenance; older generation.

### 2.2 `openinference-instrumentation-langchain`

- PyPI: `openinference-instrumentation-langchain` v0.1.73 (PyPI "Production/Stable", Python >=3.10,<3.15), Apache-2.0, in the `Arize-ai/openinference` repo (1,180+ stars overall).
- README: https://github.com/Arize-ai/openinference/blob/main/python/instrumentation/openinference-instrumentation-langchain/README.md
- Activation (hooks `langchain_core`, so covers LangChain 1.x, LangChain Classic, and all partner packages):

```python
from openinference.instrumentation.langchain import LangChainInstrumentor
LangChainInstrumentor().instrument()
```

  Uses the global `TracerProvider` by default; accepts `tracer_provider=`, `config=TraceConfig(...)`, `separate_trace_from_runtime_context=True` (start a fresh trace per root span — important for background workers / Celery).

- What it captures automatically (from `_tracer.py`, v0.1.73):
  - Span kinds: `openinference.span.kind` derived from LangChain run_type (`LLM`, `CHAIN`, `TOOL`, `RETRIEVER`, `EMBEDDING`); run name containing "agent" → `AGENT`; unknown run types (e.g. `parser`) → `CHAIN` (matching the JS instrumentor).
  - `input.value` / `output.value` (+ mime types), prompts and chat messages (`llm.prompts.*`, `llm.input_messages.*`, `llm.output_messages.*`) — **captured by default; privacy opt-out via `TraceConfig` masking**, not opt-in.
  - `llm.model_name`, `llm.provider`, `llm.system` (via provider maps — note gaps: deepseek, fireworks, xai, perplexity, huggingface map to `_NA`), `llm.invocation_parameters`, `llm.finish_reason` (non-streaming and streaming paths).
  - Token usage from `UsageMetadata` / `response_metadata` (OpenAI- and Anthropic/Gemini-style keys): `llm.token_count.prompt/completion/total`, cache read/write, reasoning, audio.
  - Tool calls: `message.tool_calls.*` in output messages, `llm.tools.*` schemas, `llm.function_call`.
  - Retrieval documents (`retrieval.documents.*`), metadata (`metadata` JSON), prompt template attributes.
  - Errors: `on_*_error` callbacks → `span.record_exception()` (exception event with type/message/stacktrace) and span status `ERROR` with `run.error` as description; otherwise status `OK`. Handles LangGraph `on_interrupt`/`on_resume` events (no-op).
- Does NOT capture: cost attributes (`llm.cost.*`), retries, any failure-classification attributes, workflow/session boundaries (that's the app's job via `using_attributes`).

### 2.3 `openinference-instrumentation-llama-index`

- PyPI: `openinference-instrumentation-llama-index` v4.4.8 ("Production/Stable"), Apache-2.0. Version matrix: v4.x → llama-index >=0.12.3.
- README: https://github.com/Arize-ai/openinference/blob/main/python/instrumentation/openinference-instrumentation-llama-index/README.md
- Activation:

```python
from openinference.instrumentation.llama_index import LlamaIndexInstrumentor
LlamaIndexInstrumentor().instrument(tracer_provider=tracer_provider)
```

- What it captures automatically (from `_callback.py`, v4.4.8 — implements a `BaseCallbackHandler`):
  - Span-kind mapping from `CBEventType`: `LLM`→LLM, `EMBEDDING`→EMBEDDING, `RETRIEVE`→RETRIEVER, `FUNCTION_CALL`→TOOL, `AGENT_STEP`→AGENT, `RERANKING`→RERANKER, everything else → CHAIN (`None` → UNKNOWN).
  - Inputs/outputs (`input.value`/`output.value`), prompts, messages, `llm.model_name`, invocation parameters (temperature, max_tokens, additional_kwargs), prompt template attributes, retrieval documents, tool call messages, token counts from usage objects (OpenAI/Anthropic/Gemini-style keys incl. cache read/write, reasoning, audio).
  - Errors: exceptions carried in `EventPayload.EXCEPTION` are recorded (`span.record_exception`) and the span status is set to `ERROR` with `"Type: message"` description; otherwise `OK`. Streaming responses are wrapped (`_ResponseGen`) so tokens are accumulated, status set on stream error, and the span ends when the stream finishes.
- Does NOT capture: cost attributes, retries, failure classification, session/workflow boundaries.

### 2.4 Provider-level instrumentors (relevant to what the SDK inherits)

`openinference-instrumentation-openai`, `-anthropic`, `-litellm`, etc. exist for direct SDK calls. Framework instrumentors above delegate model-call capture to the framework's own callback/tracer systems, so you should NOT double-instrument provider SDKs (duplicate/competing spans and token undercounting for streaming — see openinference issue #2268).

---

## 3. Phoenix ingestion

- Phoenix ingests standard OTLP. HTTP endpoint `http://localhost:6006/v1/traces` (default local serve); also gRPC. Any OTel collector can sit in front.
- `python -m phoenix.server.main serve` runs the server+collector (per OpenInference quickstarts); `phoenix.launch_app()`/`px.launch_app()` does the same in-process.
- Cost: **Phoenix computes costs itself** — from `llm.token_count.prompt`/`llm.token_count.completion` + `llm.model_name`/`llm.provider` + its built-in model-pricing table (OpenAI, Anthropic, Gemini, Cerebras, Fireworks, Groq, Moonshot; custom models/prices configurable in Settings → Models; per-1M-token input/output pricing, cache-read/write and reasoning-token pricing). Costs roll up to span, trace, session, experiment, and project level. Phoenix will (as of mid-2026, open issue #13655) NOT honor externally supplied span costs on non-LLM spans; token-derived pricing is the supported path. So: **our SDK only needs to emit accurate token counts + model + provider; cost computation stays in the backend.**
- Token counts: Phoenix/AX can also backfill token counts itself (user-provided → tiktoken → character estimate) when `llm.token_count.*` is missing, but relies on the instrumentors' counts when present.
- Failures: **Phoenix does not classify failures automatically.** It stores spans as-is and surfaces span status codes (`OK`/`ERROR`/`UNSET`), `exception.*` events, and filterable span kinds. Failure-mode analysis is done via manual annotations, Alyx (AI), or Arize Skills — i.e. downstream of ingestion. Failure classification is therefore a backend concern for our platform, but the SDK must supply the raw material: span status + exception type/message/stacktrace.
- Project routing: OTLP header-based project routing (`OTLP Project Routing via HTTP Header`, Phoenix ≥15.5.0) lets one endpoint fan out to projects.
- Span status codes and `openinference.span.kind` are first-class filters in the REST API/CLI (`px spans --span-kind --status-code`).

---

## 4. Gaps for our SDK (concrete)

Legend: ✅ exists in conventions/instrumentors · ➕ must be added by our SDK.

### 4.1 LLM calls, prompts/responses, latency, token usage
- ✅ `llm.*` message/token/model/provider attributes; latency = native OTel span duration (no attribute needed).
- ✅ Both framework instrumentors capture prompts/responses by default; `TraceConfig` (hide_inputs/hide_outputs/hide_input_messages/hide_output_messages/base64_image_max_length, env vars per `spec/configuration.md`) masks them.
- ➕ **Opt-in prompt/response capture**: defaults in existing instrumentors capture full payloads. Our SDK contract requires opt-in. Add an SDK-level gate (default OFF or ON per config) that controls whether to rely on instrumentor payload capture (or apply a `TraceConfig` that hides and lets the SDK re-annotate selectively). No convention change needed — `TraceConfig` covers it.

### 4.2 Costs
- ✅ Convention attributes `llm.cost.*` exist but are NOT emitted by the LangChain/LlamaIndex instrumentors (no pricing in framework layers).
- ➕ SDK should NOT compute cost (backend does). It must guarantee complete `llm.token_count.prompt/completion` (+cache/reasoning details) and accurate `llm.model_name` + `llm.provider` on every LLM span — provider mapping gaps in the LangChain instrumentor (`deepseek`, `fireworks`, `xai`, `perplexity`, `huggingface` → unset) may need SDK-side normalization/override for cost correctness.

### 4.3 Errors / failures / retries
- ✅ Span status (`ERROR` + description) and `exception.*` events from both instrumentors.
- ➕ No structured failure metadata anywhere: add SDK attributes such as `sdk.error.type` / `sdk.error.kind` (e.g. `provider_error`, `tool_error`, `timeout`, `rate_limit`), derived error category, and (opt-in) retry metadata (attempt number, `sdk.retry.count`, `sdk.retry.of` linkage) — **no OpenInference convention exists for these**, so we must define our own namespaced attributes. Backend classification consumes them; exception events remain the fallback.

### 4.4 Workflow steps / agents / business context
- ✅ CHAIN/AGENT/TOOL span kinds exist and are emitted by both instrumentors (AGENT via LangChain run-name heuristic or LlamaIndex `AGENT_STEP`).
- ➕ **Workflow/agent boundary semantics**: no instrumentor opens an outer "workflow" span or sets `session.id`/`user.id`/`agent.name`. These are available via `openinference-instrumentation` context helpers (`using_session`, `using_user`, `using_metadata`, `using_tag`, `using_prompt_template`, `using_attributes`) — SDK should expose a `workflow_span()` / `run()` wrapper that opens a CHAIN/AGENT span, sets session/user/agent identity, and nests framework spans under it.
- ➕ Business-context attributes (`metadata`, `tag.tags`) exist as conventions; SDK must provide a structured way to set them at workflow start (the context-manager helpers exist, so this is packaging, not new conventions).

### 4.5 Tool calls
- ✅ TOOL spans + `tool.*`/`message.tool_calls.*` captured by both instrumentors.
- ➕ No gap for v1 capture; SDK may add `tool.error`/`tool.retry` attribution on top (see 4.3).

### 4.6 Retrievers / embeddings / rerankers
- ✅ Covered by both instrumentors (`retrieval.documents.*`, `embedding.*`, `reranker.*`). No SDK work needed beyond ensuring they flow.

### 4.7 Transport / packaging
- ➕ SDK must own: `TracerProvider` + `BatchSpanProcessor` + `OTLPSpanExporter` (HTTP `/v1/traces`) wiring, `Resource` attributes (`service.name`, `service.version`, `deployment.environment`), graceful `shutdown()`, and the `TracerProvider` passed into both instrumentors. `separate_trace_from_runtime_context=True` for background/worker contexts.
- ➕ Avoid double instrumentation: if customers use our SDK, do not also load provider-level OpenInference instrumentors (nested/duplicate spans, streaming token miscounts — issue #2268).
- ➕ Sampling/redaction defaults and `TraceConfig` propagation are SDK-level decisions (the conventions only define the knobs).

### 4.8 Source URLs (key)
- Spec: https://github.com/Arize-ai/openinference/blob/main/spec/semantic_conventions.md
- Rendered spec: https://arize-ai.github.io/openinference/spec/semantic_conventions.html
- LangChain instrumentor: https://github.com/Arize-ai/openinference/blob/main/python/instrumentation/openinference-instrumentation-langchain/README.md (+ `_tracer.py`)
- LlamaIndex instrumentor: https://github.com/Arize-ai/openinference/blob/main/python/instrumentation/openinference-instrumentation-llama-index/README.md (+ `_callback.py`)
- Common utilities (context managers, TraceConfig): https://github.com/Arize-ai/openinference/blob/main/python/openinference-instrumentation/README.md
- Phoenix cost tracking: https://arize.com/docs/phoenix/tracing/how-to-tracing/cost-tracking
- Phoenix OTel/OpenInference overview: https://arize.com/docs/phoenix/tracing/concepts-tracing/otel-openinference/overview
- Phoenix generic-cost issue (server-side pricing only): https://github.com/Arize-ai/phoenix/issues/13655
- OTel registry: https://opentelemetry.io/ecosystem/registry/
- OTel GenAI semconv: https://opentelemetry.io/docs/specs/semconv/gen-ai/ ; OTel vs OpenInference relation issue: https://github.com/Arize-ai/openinference/issues/2130
- OpenInference GitHub: https://github.com/Arize-ai/openinference (~1,180 stars, Apache-2.0)