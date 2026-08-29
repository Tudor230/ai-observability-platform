# SDK Plan (v1)

Python observability SDK for the AI Observability Platform. Focus of the planning effort; every decision here traces to a wayfinder ticket under `.scratch/sdk/issues/` (linked in [Decision index](#decision-index)).

## 1. Purpose

Teams register an AI project, get an API key, install the SDK, and automatically receive observability for their LLM/agent workflows. The SDK:

- Captures LLM calls, prompts/responses (opt-in), latency, token usage, tool calls, workflow steps, agents, errors/failures, retries.
- Emits OpenInference semantic conventions over OTLP to a Phoenix backend (or the platform's collector later).
- Records usage and failure material; the **backend** computes cost and classifies failures.

**Key product principle:** teams never interact with the observability infrastructure. Register → get API key → initialize SDK → observability appears.

## 2. Scope (v1)

- Python only.
- Reuses OpenInference instrumentors for LangChain and LlamaIndex; no custom tracing of frameworks.
- Manual workflow boundary API (no auto-detection).
- Prompt/response capture opt-in.
- No sampling, no gRPC, no LangGraph first-class support.

## 3. Architecture

```text
Application (LangChain / LlamaIndex / plain Python)
        |
        v
SDK core (workflow wrapper, span helper, failure attrs, retry inference, provider normalization)
        |
        v
TracerProvider + BatchSpanProcessor + OTLPSpanExporter (HTTP /v1/traces)
        |
        v
Phoenix (ingest, storage, token counts, server-side cost)
```

- SDK owns the `TracerProvider`, passed into both OpenInference instrumentors.
- Resource attributes: `service.name`, `service.version`, `deployment.environment` (OTel env conventions).
- Never double-instrument: SDK warns at init if another LangChain/LlamaIndex/provider instrumentor is already active (OpenInference issue #2268).

## 4. Configuration & initialization

```python
from ai_observability import init

init(
    api_key="...",        # env: AI_OBSERVABILITY_API_KEY
    endpoint="http://localhost:6006",   # env: AI_OBSERVABILITY_ENDPOINT
    project_id="proj-1",  # env: AI_OBSERVABILITY_PROJECT_ID
    capture_prompts=False,
)
```

- Explicit args override env vars (12-factor).
- API key + project id ride as **custom OTLP headers** — the platform's ingest authenticates and routes by them; works with Phoenix today.
- Transport: OTLP HTTP `/v1/traces`.
- `capture_prompts` gates payload capture globally (see §7); per-workflow override available.

## 5. Trace model

### 5.1 Workflow boundary

Manual wrapper only — context manager and decorator, sync and async:

```python
from ai_observability import workflow, span

# Context manager
with workflow(
    name="checkout",
    client_id="client-42",
    workflow_id="order-123",
    version="v2",
    context={"channel": "web", "ticket_id": "INC-12345"},
) as wf:
    result = run_agent()

# Decorator
@workflow(name="checkout", client_id="client-42")
async def run_checkout(order_id):
    return await agent.run(order_id)
```

- **Span kind**: workflow root = OpenInference `CHAIN`. Agents appear as `AGENT` spans (from the instrumentors) nested beneath; LLM/TOOL/RETRIEVER spans under agents. No `WORKFLOW` kind exists — the backend identifies workflow roots by the SDK's namespaced attributes.
- **Nesting**: workflows can nest (child CHAIN under parent CHAIN) for multi-stage pipelines.
- **Identity**: span name = provided workflow name; `session.id` = `workflow_id` automatically; `user.id` only when explicitly passed.
- **Attributes**:
  - Predefined, namespaced: `client_id`, `project_id` (from init), `workflow_id`, `version` — structured input for the backend's cost attribution.
  - Flexible: `context` (any JSON-serializable dict) → OpenInference `metadata`.

### 5.2 Manual span helper

For business steps outside framework coverage (validation, final response, plain API calls):

```python
with span("validate_output", context={"checks": 3}):
    validate(result)
```

- Emits a `CHAIN` span under the active workflow; name + optional context only in v1.

### 5.3 Trace hierarchy (OTLP)

```text
workflow (CHAIN)                       <- session.id, client_id, project_id, workflow_id, version, metadata
├── agent run (AGENT)                  <- from instrumentors
│   ├── LLM call (LLM)                 <- model, provider, tokens, messages, error material
│   └── Tool call (TOOL)               <- tool name, parameters, error material
├── retriever (RETRIEVER)              <- documents
├── custom step (CHAIN)                <- via span()
└── nested workflow (CHAIN)            <- if nested
```

## 6. Failure & usage capture

The SDK records **raw material**; the backend holds the authoritative failure taxonomy and cost engine.

### 6.1 Errors

- Rely on instrumentors' exception events (`exception.type/message/stacktrace`) + span status `ERROR`.
- SDK adds namespaced attributes on the failing span: `sdk.error.type` (exception class), `sdk.error.message`.
- The span kind identifies the failing layer (LLM/TOOL/RETRIEVER/CHAIN).
- **Classification hints**: best-effort `sdk.error.kind` where cheaply detectable at capture (timeouts, rate limits, invalid JSON on output). Backend may trust or override.
- **Root propagation**: workflow root gets `ERROR` status when any descendant failed, plus `sdk.error.kind` of the first/primary failure — "workflow #123: FAILED" visible at a glance.

### 6.2 Token usage & provider accuracy

- SDK validates `llm.token_count.prompt/completion` (+ cache/reasoning details) exist on every LLM span, sanity-checks totals, and **backfills** missing counts (tiktoken/character-estimate chain).
- SDK ships a small **provider-normalization map** (deepseek, fireworks, xai, perplexity, huggingface, ...) and fills `llm.provider` when the LangChain instrumentor left it unset.
- No `llm.cost.*` emission — Phoenix computes cost server-side from token counts + pricing table (it does not honor external span costs).

### 6.3 Prompt/response capture (opt-in)

- Global `init(capture_prompts=False)` default **off**; per-workflow override.
- When on, `TraceConfig` keeps payloads (messages, inputs/outputs) on LLM/TOOL/RETRIEVER spans.

### 6.4 Retries

- `sdk.retry.of`: from `llm.invocation_parameters` where frameworks expose `max_retries` (LangChain/Anthropic; ChatOpenAI does not).
- `sdk.retry.count`: inferred by an SDK-owned `SpanProcessor` that counts failed-attempt sibling LLM spans when the workflow root ends.
- Framework-internal retries otherwise appear as repeated sibling ERROR spans (unlabeled); the backend can derive them too.
- Exact per-attempt counts via opt-in httpx event-hook client: future work.

## 7. Auto-instrumentation

### 7.1 LangChain

- Reuse `openinference-instrumentation-langchain` (v0.1.73+) with our TracerProvider.
- **v1 coverage**: LLM calls, agents (AGENT via run-name heuristic), tools, retrievers, prompt templates.
- **Not covered in v1**: memory; rerankers (surface only as plain CHAIN spans — deferred); **LangGraph** (only partial CHAIN coverage today; interrupt/resume unhandled) — documented limitation.
- Spans nest under the manual workflow root via context propagation. A small documented **reclassification hook** corrects AGENT spans the heuristic misfires on.
- Streaming: rely on the instrumentor's streaming paths (token accumulation, status on stream error); sync + async.

### 7.2 LlamaIndex

- Reuse `openinference-instrumentation-llama-index` (v4.x; llama-index >= 0.12.x).
- **v1 coverage**: full sweep — LLM, query engines/chains (CHAIN), retrievers (RETRIEVER), embeddings (EMBEDDING), agents (AGENT via `AGENT_STEP`), tools (TOOL via `FUNCTION_CALL`), rerankers (RERANKER).
- Same nesting, same reclassification hook, same double-instrumentation warning.
- Both frameworks can mix under one workflow root.

## 8. Export reliability

Observability must never break the app:

1. Wrapper/instrumentor exceptions never propagate into application code.
2. Export on background threads — the app thread never blocks on the network.
3. Queue overflow **drops** spans (warning logged) — never blocks, never unbounded.
4. Export/ingest failures are logged, never raised.

- **Batching/retry**: OTel defaults — BatchSpanProcessor (5s interval, 512 spans/batch, 2048 queue); exporter retries with exponential backoff.
- **Flush**: `atexit` hook flushes pending spans for short-lived processes; explicit `flush()` for app shutdown; servers rely on the normal batch flow.
- **Sampling**: none in v1 (mock workflows need complete traces); rate sampling documented as future work.
- **Background workers**: use `separate_trace_from_runtime_context=True` so each worker task starts a fresh trace under the active workflow context.

## 9. Mock workflows (deterministic test harness)

Validates that capture and (later) classification actually work. Runs through the **real** SDK + instrumentors with framework-native fake models.

### 9.1 Form

- Python scenarios: LangChain `FakeChatModel` / LlamaIndex `MockLLM` returning fixed responses and fixed usage metadata.
- Bundled in the SDK repo; runnable via **pytest** and a **CLI** printing a pass/fail report with failing assertions.
- Programmatic assertions only (no golden files): trace shape, attributes, failure propagation.
- Runs in CI on every SDK change — the SDK's regression gate.

### 9.2 Failure catalog (v1)

| Scenario | Signal |
|---|---|
| Tool timeout | TOOL span fails; retry inference exercised |
| LLM error | ERROR LLM span + exception event |
| Invalid JSON | Invalid-output signal on a structured-output step |
| Retrieval failure | RETRIEVER span fails |
| High latency | Controlled fake sleep; latency visible |
| Rate limit | 429-style error; rate-limit hint |
| Retry-then-success | `sdk.retry.count > 0` asserted |

### 9.3 Fixed cost

Fake providers return fixed token counts → token/cost math is deterministic. v1 asserts token counts; the same traces feed backend cost computation and failure classification once they exist (KPIs in `docs/05`).

## 10. Deferred / future work

- Plain OpenAI/Anthropic client auto-instrumentation (pending framework-coverage gaps)
- Packaging/distribution (PyPI, versioning) and the public package/import name (sketched as `ai_observability`)
- Async/streaming support specifics beyond instrumentor behavior
- Redaction mechanics for opt-in prompt capture
- Exact per-attempt retry counts (opt-in httpx event-hook client)
- LangGraph first-class support; LangChain memory and reranker tracing
- Post-v1 frameworks (CrewAI, ...); non-Python SDKs
- Rate sampling
- Automated evaluation beyond mock workflows (LLM-as-judge style)

## 11. Out of scope (this plan)

- Building the platform backend (trace processing, cost engine, failure classification, alerting) — separate plan
- Phoenix deployment and dashboard — separate plans
- The business agents being monitored; model training/fine-tuning

## 12. Decision index

Every decision above was resolved on the wayfinder map `.scratch/sdk/`:

| Ticket | Decision |
|---|---|
| [01 — OpenInference coverage research](../.scratch/sdk/issues/01-openinference-coverage.md) | Conventions/instrumentor landscape; what the SDK must add; Phoenix behavior |
| [02 — SDK trace model & manual API](../.scratch/sdk/issues/02-sdk-trace-model.md) | Workflow wrapper, CHAIN root, attributes, span helper, identity |
| [03 — SDK config & export reliability](../.scratch/sdk/issues/03-sdk-config-export.md) | init/env, OTLP headers, transport, isolation, batching, flush, no sampling |
| [04 — Failure & usage capture schema](../.scratch/sdk/issues/04-failure-usage-capture.md) | Error material, hints, token validate/backfill, provider normalization, prompt opt-in, root propagation |
| [05 — LangChain instrumentation scope](../.scratch/sdk/issues/05-langchain-instrumentation.md) | Reuse instrumentor; coverage; LangGraph/memory/reranker exclusions |
| [06 — LlamaIndex instrumentation scope](../.scratch/sdk/issues/06-llamaindex-instrumentation.md) | Reuse instrumentor; full coverage; nesting + reclassification hook |
| [07 — Mock workflows design](../.scratch/sdk/issues/07-mock-workflows.md) | Harness form, failure catalog, token assertions, CI gate |
| [09 — Retry observability research](../.scratch/sdk/issues/09-retry-observability.md) | What's observable; SpanProcessor inference mechanism |

Research findings: `.scratch/sdk/research/01-openinference-coverage.md`, `.scratch/sdk/research/09-retry-observability.md`.