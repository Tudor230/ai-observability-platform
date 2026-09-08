# ai-observability-sdk

Python observability SDK for the AI Observability Platform (phase 1).
Implements [`plans/sdk.md`](../plans/sdk.md): manual workflow boundaries,
LangChain + LlamaIndex auto-instrumentation, failure/usage capture, OTLP HTTP
export into Phoenix (PostgreSQL-backed), and a deterministic mock-workflow
regression suite.

## Quickstart

```python
from ai_observability import init, workflow, span

init(
    api_key="...",             # env: AI_OBSERVABILITY_API_KEY
    endpoint="http://localhost:6006",   # env: AI_OBSERVABILITY_ENDPOINT
    project_id="proj-1",       # env: AI_OBSERVABILITY_PROJECT_ID
    capture_prompts=False,     # opt-in payload capture
)

# Context manager (sync) / @workflow decorator (sync + async)
with workflow(
    name="checkout",
    client_id="client-42",
    workflow_id="order-123",
    version="v2",
    context={"channel": "web"},
) as wf:
    run_agent()                # LangChain/LlamaIndex spans nest under it

# Manual step for non-framework code
with span("validate_output", context={"checks": 3}):
    validate(result)

# App shutdown: flush pending spans
ai_observability.flush()
```

Explicit args override env vars. The API key and project id ride as custom
OTLP headers; Phoenix routes spans to the project via `x-project-name`.

## Trace storage: Phoenix + PostgreSQL

```bash
cd dev
docker compose up -d --wait          # Phoenix :6006 + Postgres :5432
```

Phoenix stores spans in Postgres (`PHOENIX_SQL_DATABASE_URL`), so traces are
inspectable with SQL or the Phoenix UI (http://localhost:6006):

```bash
uv run python dev/inspect_traces.py                # latest workflow roots
uv run python dev/inspect_traces.py --trace <id>   # full span list
uv run python dev/inspect_traces.py --sql          # sample SQL
```

The workflow root CHAIN span carries the business context as nested jsonb in
`spans.attributes`: `sdk.client_id`, `sdk.project_id`, `sdk.workflow_id`,
`session.id`, `metadata` — plus `sdk.error.*` / `sdk.retry.*` when applicable.

## Mock workflows (regression suite, plans/sdk.md §9)

Deterministic scenarios through the real SDK + instrumentors with framework
fake models (fixed responses, fixed token counts, scripted failures):

```bash
uv run pytest                          # 97 tests, offline (in-memory export)
uv run aiobs-mock                      # pass/fail CLI report (18 scenarios)
uv run aiobs-mock --endpoint http://localhost:6006   # ...and export for real
```

Failure catalog covered: LLM error, tool timeout (+ retry inference), invalid
JSON, retrieval failure, high latency, rate limit, retry-then-success — plus
LangGraph: basic node tracing, interrupt, resume, and streaming interrupt.

## Real demo (not mocked)

`examples/checkout_agent.py` runs a checkout-support agent with **real LLM
calls** (LangChain `ChatOpenAI` over HTTP — OpenAI, DeepSeek, Ollama, LM
Studio, ...), a tool call, a manual validation span, and exports the trace:

```bash
cd dev && docker compose up -d --wait
cd .. && OPENAI_API_KEY=sk-... uv run python examples/checkout_agent.py \
    "Where is my order ORD-1234?" --capture-prompts
```

See [`examples/README.md`](examples/README.md) for provider setup.

A richer RAG variant — `examples/rag_checkout_agent.py` — layers RETRIEVER +
AGENT (LLM/TOOL) + compose + validation spans under one workflow root for the
MVP demo (`RETRIEVER`/`AGENT`/`LLM`/`TOOL`/`CHAIN` kinds). The LlamaIndex
counterpart — `examples/rag_order_support_llamaindex.py` — runs a deep
retrieve → tool → synthesize → validate flow (`RETRIEVER`/`TOOL`/`LLM`/`CHAIN`).

A LangGraph human-in-the-loop demo — `examples/langgraph_refund_approval.py` —
builds a `StateGraph` (LLM routing, `@tool` nodes, an `interrupt()` approval
node) and shows the HITL capture: the interrupt and resume runs export as two
traces grouped under one Phoenix session with `sdk.hitl.*` attributes. It runs
offline with `--mock` (no API key needed). See `examples/README.md`.

## What the SDK emits

* Workflow roots as OpenInference `CHAIN` with `sdk.*` business attributes;
  framework spans (AGENT/LLM/TOOL/RETRIEVER) nest beneath via context.
* `sdk.error.type/message` from exception events, best-effort `sdk.error.kind`
  hints (rate_limit, timeout, invalid_output, tool_error, provider_error);
  failed workflows propagate `ERROR` status + primary failure kind to the root.
* Retry inference: `sdk.retry.count` (failed-attempt LLM/TOOL spans) and
  `sdk.retry.of` (max_retries from invocation params where exposed).
* Token counts validated/backfilled (deterministic character estimate by
  default; optional tiktoken via `AI_OBSERVABILITY_BACKFILL_TIKTOKEN=1`);
  provider normalization for models the LangChain instrumentor misses.
* **LangGraph**: traced via the LangChain instrumentor (nodes as CHAIN/AGENT
  with `metadata.langgraph_node`). Human-in-the-loop is captured automatically
  (`sdk.hitl.*` on the workflow root): interrupt payload, resume value, thread
  id, interrupting node, checkpoint id. Interrupts are not errors — a
  paused-for-approval workflow stays OK with no `sdk.error.*`. For Phoenix
  session grouping, pass the LangGraph `thread_id` as `workflow_id`.
* Payload redaction: `capture_prompts` is off by default; per-workflow
  override via `workflow(..., capture_prompts=True)`. `sdk.hitl.*` is always
  captured (it is operational data, not prompt payload).

The SDK records raw material — the backend (next phase) holds the
authoritative failure taxonomy and cost engine.

## Layout

```
src/ai_observability/    the SDK (config, tracing, workflow API, enrichment)
src/mock_workflows/      scenarios + fakes + CLI runner
tests/                   unit tests, scenario suite, e2e (docker)
dev/                     docker-compose (postgres + phoenix), inspect tooling
```

## Development

```bash
uv sync --group dev
uv run pytest
AI_OBSERVABILITY_E2E=1 uv run pytest -m e2e   # requires `docker compose up -d --wait`
```