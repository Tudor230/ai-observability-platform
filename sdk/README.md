# ai-observability-sdk

Python observability SDK for the AI Observability Platform (phase 1).
Implements [`plans/sdk.md`](../plans/sdk.md): manual workflow boundaries,
LangChain + LlamaIndex + raw Ollama + raw Groq + raw ChromaDB client
auto-instrumentation, failure/usage
capture, OTLP HTTP export into Phoenix (PostgreSQL-backed), and a deterministic
mock-workflow regression suite.

> **Adding the SDK to an existing agent/app?** Follow
> [`INTEGRATION.md`](INTEGRATION.md) — a step-by-step guide (smoke test →
> init → workflow boundary → verification → troubleshooting).

## Install

```bash
pip install ai-observability-sdk
```

The SDK ships the OpenInference instrumentors but **not** the frameworks
themselves: install the LangChain/LlamaIndex/Ollama/Groq/ChromaDB versions your
app already uses. A framework that is not installed is skipped silently at
`init()`.

The bundled mock-workflow suite (`aiobs-mock`) needs its framework extras:

```bash
pip install "ai-observability-sdk[mock]"
```

## Quickstart

```python
from ai_observability import init, workflow, span

init(
    api_key="...",             # env: AI_OBSERVABILITY_API_KEY — the ingest identity
    endpoint="http://localhost:6006",   # env: AI_OBSERVABILITY_ENDPOINT
    capture_prompts=False,     # opt-in payload capture
)

# Context manager (sync) / @workflow decorator (sync + async)
with workflow(
    name="checkout",
    workflow_id="order-123",
    version="v2",
    context={"channel": "web"},
) as wf:
    run_agent()                # LangChain/LlamaIndex/Ollama/Groq/ChromaDB spans nest under it

# Manual step for non-framework code
with span("validate_output", context={"checks": 3}):
    validate(result)

# App shutdown: flush pending spans
ai_observability.flush()
```

Explicit args override env vars. The **API key is the ingest identity**
(ADR-0008) — the platform resolves the project from it and that is all a
production integration needs. `project_id` / `AI_OBSERVABILITY_PROJECT_ID` is a
**debug/testing override and should not be used in production**: it only routes
traces inside a local Phoenix instance (`x-project-name` header +
`openinference.project.name` resource attribute, so Phoenix groups correctly on
any version), and the SDK warns when it is set.

## Trace storage: Phoenix + PostgreSQL

```bash
docker compose up -d --wait postgres phoenix   # from the repo root
```

Phoenix stores spans in Postgres (`PHOENIX_SQL_DATABASE_URL`) on the **shared
platform instance** (`:5432`; databases `phoenix` for traces, `aiobs` for the
backend, `aiobs_test` for backend tests) — the SDK tooling and the backend use
the same instance. Traces are inspectable with SQL or the Phoenix UI
(http://localhost:6006):

```bash
uv run python dev/inspect_traces.py                # latest workflow roots
uv run python dev/inspect_traces.py --trace <id>   # full span list
uv run python dev/inspect_traces.py --sql          # sample SQL
```

The workflow root CHAIN span carries the business context as nested jsonb in
`spans.attributes`: `sdk.project_id` (debug runs only), `sdk.workflow_id`,
`session.id`, `metadata` — plus `sdk.error.*` / `sdk.retry.*` when applicable.

## Mock workflows (regression suite, plans/sdk.md §9)

Deterministic scenarios through the real SDK + instrumentors with framework
fake models (fixed responses, fixed token counts, scripted failures):

```bash
uv run pytest                          # 161 tests, offline (in-memory export)
uv run aiobs-mock                      # pass/fail CLI report (28 scenarios)
uv run aiobs-mock --endpoint http://localhost:6006   # ...and export for real
```

Point the suite straight at the platform backend's OTLP ingest (key-only is all
it needs) or at Phoenix with project routing via the debug-only `--project-id`:

```bash
uv run aiobs-mock --endpoint http://localhost:8000 --api-key <project-api-key>
# Debug override for Phoenix dev routing: --project-id sets the
# openinference.project.name resource attribute (and the x-project-name header):
uv run aiobs-mock --endpoint http://localhost:6006 --project-id proj-1
```

Failure catalog covered: LLM error, tool timeout (+ retry inference), invalid
JSON, retrieval failure, high latency, rate limit, retry-then-success — plus
LangGraph: basic node tracing, interrupt, resume, and streaming interrupt; plus
raw Ollama chat: happy path, rate-limit error, redaction, and streaming; plus
raw ChromaDB query: retrieval span, invalid filter, and redaction; plus raw
Groq chat: happy path, rate-limit error, and redaction.

## Real demo (not mocked)

`examples/checkout_agent.py` runs a checkout-support agent with **real LLM
calls** (LangChain `ChatOpenAI` over HTTP — OpenAI, DeepSeek, Ollama, LM
Studio, ...), a tool call, a manual validation span, and exports the trace:

```bash
docker compose up -d --wait postgres phoenix   # from the repo root
cd sdk && OPENAI_API_KEY=sk-... uv run python examples/checkout_agent.py \
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
node) and shows the HITL capture: the interrupt and resume runs join **one
trace** (deterministic trace id from `workflow_id` = thread id) with
`sdk.hitl.*` attributes. It runs offline with `--mock` (no API key needed).
See `examples/README.md`.

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
* **Raw Ollama client**: plain `ollama.chat` / `Client.chat` / `AsyncClient.chat`
  calls (streaming included) become OpenInference **LLM** spans with
  `llm.provider=ollama`, model, token counts (`prompt_eval_count`/`eval_count`),
  input/output messages, and exception events. Instrument before the first chat
  call; skipped silently when the `ollama` package is not installed. Local
  models price at $0 via the backend's seeded zero-rate default row.
* **Raw Groq client**: plain `Groq().chat.completions.create(...)` calls
  become OpenInference **LLM** spans (`Completions`) with `llm.provider=groq`,
  model, token counts from the response `usage`, input/output messages, and
  exception events (`groq.RateLimitError` → `rate_limit`). Streaming yields one
  span but upstream does not accumulate content/usage. Skipped silently when
  the `groq` package is not installed; the backend seeds Groq's gpt-oss list
  rates so they price out of the box.
* **Raw ChromaDB client**: plain `collection.query(...)` calls become
  OpenInference **RETRIEVER** spans (`chroma.query`) with `input.value` (query
  text), `retrieval.documents.*` (id/content/metadata/distance), `output.value`
  (the documents as a JSON array, like upstream retriever spans), and
  `db.system=chroma` / `db.operation` / `db.collection.name`, plus an exception
  event + ERROR status on failure. The SDK owns this interceptor (OpenInference
  has no ChromaDB instrumentor); sync `Collection.query` only, skipped silently
  when `chromadb` is not installed. Inside a LangChain/LangGraph run the span
  parents under the active node (the callback tracer does not attach its spans
  to the OTel context), otherwise under the workflow root.
* **Databricks AI Search**: `similarity_search(...)` on `AISearchIndex` /
  `AsyncAISearchIndex` (and legacy `VectorSearchIndex` imports) becomes an
  OpenInference **RETRIEVER** span named `databricks.ai_search.query`, with
  query text, index/endpoint identity, query type, result count, and the
  returned rows as `retrieval.documents.*` + `output.value`. Nests under the
  active LangGraph node when one is running; skipped silently when
  `databricks-ai-search` is not installed.
* Payload redaction: `capture_prompts` is off by default; per-workflow
  override via `workflow(..., capture_prompts=True)`. `sdk.hitl.*` is always
  captured (it is operational data, not prompt payload).
* **Loop detection (ADR-0014)**: identical LLM/TOOL calls are measured live.
  Each call gets a salted, run-scoped `sdk.call.sig` (HMAC of the call input —
  never the payload itself); when a call repeats (≥3 by default) or completes a
  signature-equal 2–4 step cycle, the span is marked with `sdk.loop.signal` /
  `sdk.loop.repeat_count` and the workflow root carries
  `sdk.loop.tool_repeats` / `llm_repeats` / `cycle_repeats` evidence counts.
  Retried attempts and failed calls never count. The backend re-derives the
  authoritative execution flag from the exported signatures; the SDK's marks
  are trace-UI context.

The SDK records raw material — the backend (next phase) holds the
authoritative failure taxonomy and cost engine.

## Loop detection

Agents can get stuck repeating themselves without any span erroring; the SDK
measures that repetition content-free and the platform flags it (component
tickets in `.scratch/loop-detection/`, decision in ADR-0014):

* **Signals**: `tool_repeat` (same tool + arguments), `llm_repeat` (same model
  + full input), `cycle` (consecutive repeating pattern of 2–4 calls with
  identical signatures). Name-only alternation — a normal ReAct agent — never
  flags.
* **Privacy**: signatures are HMAC-SHA256 digests over canonicalized input
  under a per-process random salt that is never exported. The digest is an
  equality token valid only within the emitting process; prompts stay local
  even with `capture_prompts=False`.
* **Off switch**: `init(loop_detection=False)` or
  `AI_OBSERVABILITY_LOOP_DETECTION=false` disables signature measurement
  entirely. Thresholds (default 3) are backend config, so tuning needs no SDK
  release.
* **Demo scenarios**: `uv run aiobs-mock --scenario loop_tool_repeat` (a stuck
  agent — expect signals and root evidence) and `--scenario loop_clean_react`
  (a healthy alternation — expect signatures but no flags); add
  `--endpoint http://localhost:8000 --api-key <key>` to see them in the
  dashboard's executions list and alerts.

## Layout

```
src/ai_observability/    the SDK (config, tracing, workflow API, enrichment)
src/mock_workflows/      scenarios + fakes + CLI runner
tests/                   unit tests, scenario suite, e2e (docker)
dev/                     inspect tooling (SQL over the shared platform Postgres)
```

## Development

```bash
uv sync --group dev
uv run pytest
uv run pytest --cov=ai_observability --cov=mock_workflows --cov-fail-under=80  # CI floor
AI_OBSERVABILITY_E2E=1 uv run pytest -m e2e   # requires the shared stack (`docker compose up -d --wait postgres phoenix` at the repo root)
```

### Releasing

Releases are tag-triggered: bump `__version__` in
`src/ai_observability/__init__.py`, commit, then push a matching tag
(`git tag sdk-v0.1.1 && git push origin sdk-v0.1.1`). The `release` workflow
runs the offline suite, builds both `aiobs-contracts` and
`ai-observability-sdk`, publishes them to PyPI via trusted publishing, and
creates the GitHub Release.