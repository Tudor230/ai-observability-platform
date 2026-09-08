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
- LangGraph traces via the LangChain instrumentor, with automatic human-in-the-loop (HITL) capture from the SDK (`sdk.hitl.*`).
- Manual workflow boundary API (no auto-detection).
- Prompt/response capture opt-in.
- No sampling, no gRPC.

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
- **Control-flow exceptions are not failures**: `GraphInterrupt`/`GraphBubbleUp`/`Command`/`ParentCommand` exception events are ignored by `is_failed()` — a LangGraph interrupt pauses, it does not fail (see §7.3).
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
- **LangGraph**: traced by the same instrumentor (LangGraph is built on `langchain-core`) — each graph run and node is a CHAIN/AGENT span carrying LangGraph's `metadata.langgraph_node`/`langgraph_step`, nested under the workflow root. Interrupts are not errors: since instrumentor `>=0.1.67`, `GraphInterrupt` matches `IGNORED_EXCEPTION_PATTERNS` so interrupted node spans get status OK. Human-in-the-loop payloads (the `interrupt()` value and the `Command(resume=...)` value) are captured automatically by the SDK — see §7.3.
- **Not covered in v1**: memory; rerankers (surface only as plain CHAIN spans — deferred).
- Spans nest under the manual workflow root via context propagation. A small documented **reclassification hook** corrects AGENT spans the heuristic misfires on.
- Streaming: rely on the instrumentor's streaming paths (token accumulation, status on stream error); sync + async.

### 7.2 LlamaIndex

- Reuse `openinference-instrumentation-llama-index` (v4.x; llama-index >= 0.12.x).
- **v1 coverage**: full sweep — LLM, query engines/chains (CHAIN), retrievers (RETRIEVER), embeddings (EMBEDDING), agents (AGENT via `AGENT_STEP`), tools (TOOL via `FUNCTION_CALL`), rerankers (RERANKER).
- Same nesting, same reclassification hook, same double-instrumentation warning.
- Both frameworks can mix under one workflow root.

### 7.3 LangGraph human-in-the-loop (auto-capture)

Phoenix has no dedicated HITL view: an interrupted run is a normal trace ending at the interrupting node (status OK), resuming is a separate trace, and the two group under a Phoenix **session** only when `session.id` equals the LangGraph thread id. The interrupt payload (the value passed to `interrupt()`) and the resume value (`Command(resume=...)`) exist **only** in the LangGraph runtime — no instrumentor writes them to a span. The SDK captures them automatically (`_langgraph.py`):

- **Boundary patch**: wrapt-wraps `Pregel.invoke/ainvoke/stream/astream` (strict pass-through — same return, same exceptions). Reads the resume value from a `Command` input and the interrupt payload from `result["__interrupt__"]` / stream marker chunks; thread id from `config.configurable.thread_id`.
- **Lifecycle hook**: patches `langgraph.callbacks` + `langgraph.pregel.main` `get_sync/async_graph_callback_manager_for_config` to inject an SDK `GraphCallbackHandler` (`langgraph >= 1.1.9`) whose `on_interrupt`/`on_resume` record the typed payloads and checkpoint id.
- **Delivery**: capture writes `sdk.hitl.*` into a bounded, lock-guarded registry in `_state` keyed by OTel `trace_id`; the enrichment layer stamps them on the workflow root at export (first-writer wins, so the two mechanisms dedup; existing root attributes are never overwritten). `sdk.hitl.node` is derived at export from the interrupting node's `metadata.langgraph_node`.
- **Interrupts are not failures**: `_errors.is_failed` ignores control-flow exception events (`GraphInterrupt`, `GraphBubbleUp`, `Command`, `ParentCommand`) — a paused-for-approval workflow keeps status OK and gets no `sdk.error.*`.

Attributes (`sdk.hitl.*`, always captured, outside payload redaction):

| Attribute | Meaning |
|---|---|
| `sdk.hitl.thread_id` | LangGraph `thread_id` from the run config |
| `sdk.hitl.interrupted` | `"true"` when the run paused on an interrupt, else `"false"` |
| `sdk.hitl.interrupt_payload` | JSON list of `interrupt()` payload values |
| `sdk.hitl.resume_value` | JSON value passed via `Command(resume=...)` |
| `sdk.hitl.node` | Name of the interrupting LangGraph node |
| `sdk.hitl.checkpoint_id` | Checkpoint id recorded by the lifecycle resume event |

Correlation: set `workflow(workflow_id=thread_id)` so `session.id` groups the interrupt and resume traces into one Phoenix session.

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
| LangGraph basic | Node CHAIN spans nest under the workflow root with `metadata.langgraph_node` |
| LangGraph interrupt | `interrupt()` pauses: root OK, `sdk.hitl.*` stamped, no `sdk.error.*` |
| LangGraph resume | `Command(resume=...)` continues the same thread: `sdk.hitl.resume_value`, same `session.id` |
| LangGraph stream | Streaming interrupt captured via the lifecycle hook |

### 9.3 Fixed cost

Fake providers return fixed token counts → token/cost math is deterministic. v1 asserts token counts; the same traces feed backend cost computation and failure classification once they exist (KPIs in `docs/05`).

## 10. Deferred / future work

- Plain OpenAI/Anthropic client auto-instrumentation (pending framework-coverage gaps)
- Packaging/distribution (PyPI, versioning) and the public package/import name (sketched as `ai_observability`)
- Async/streaming support specifics beyond instrumentor behavior
- Redaction mechanics for opt-in prompt capture
- Exact per-attempt retry counts (opt-in httpx event-hook client)
- LangChain memory and reranker tracing
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

LangGraph effort (`.scratch/langgraph/`):

| Ticket | Decision |
|---|---|
| [01 — LangGraph instrumentation](../.scratch/langgraph/issues/01-langgraph-instrumentation.md) | LangGraph traces via the LangChain instrumentor; interrupts get OK status; payload/resume values not captured by any instrumentor |
| [02 — LangGraph HITL capture](../.scratch/langgraph/issues/02-langgraph-hitl-capture.md) | Auto-interception: Pregel boundary patch + `GraphCallbackHandler` lifecycle hook; `sdk.hitl.*` scheme; control-flow filtering; registry + root stamping |
| [03 — LangGraph unit tests](../.scratch/langgraph/issues/03-langgraph-unit-tests.md) | Thorough `_langgraph.py` coverage: helpers, registry, boundary/lifecycle, control-flow, enrichment |
| [04 — LangGraph mock scenarios](../.scratch/langgraph/issues/04-langgraph-mock-scenarios.md) | `langgraph>=1.1.9` dev dep; `lg_basic`/`lg_hitl_interrupt`/`lg_hitl_resume`/`lg_hitl_stream` |
| [05 — Assemble the LangGraph plan](../.scratch/langgraph/issues/05-assemble-langgraph-plan.md) | plan/sdk.md + implementation-plan updates |

Research findings: `.scratch/sdk/research/01-openinference-coverage.md`, `.scratch/sdk/research/09-retry-observability.md`.