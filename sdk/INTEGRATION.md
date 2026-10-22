# Integrating the SDK into an existing workflow

For teams adding the platform to an agent application that already runs. You
wrap your entry point, install the package, and your LLM/tool calls show up in
the dashboard — no restructuring of the app required.

Read this once, top to bottom (15 minutes), before touching code.

---

## 1. What you get

Once integrated, every top-level `workflow()` appears in the dashboard as an
**execution** with:

- the full span tree (agent → LLM/TOOL/RETRIEVER/CHAIN spans),
- token counts and **cost** (priced by the backend's pricing table),
- **failure classification** (`rate_limit`, `timeout`, `invalid_output`,
  `tool_error`, …) with the failure tree,
- retry counts,
- **loop detection** — repeating identical tool/LLM calls are flagged with a
  `loop` badge, a filter, and an alert (`loop_executions`).

Where to look: **Engineering** (executions + trace explorer), **Manager /
Executive** (cost, workflows, agents), **Alerts**.

## 2. Prerequisites

- Python **3.10+**.
- A project on the platform with an **ingest API key**:
  dashboard → **Projects** → select the project → **Ingest API keys** →
  **Add key**. The key is shown **once** — store it in your secret manager.
  Any active key can ingest for that project; engineers/managers covering the
  project can add, rotate or delete keys later.
- The platform **endpoint** the SDK should send to. Local docker stack:
  `http://localhost:8000`. Production: your deployment's base URL. The SDK
  appends `/v1/traces` itself.

## 3. Install

```bash
pip install ai-observability-sdk
# optional, for the connectivity smoke test in step 4:
pip install "ai-observability-sdk[mock]"
# optional, accurate prompt-token backfill when the model reports none:
pip install "ai-observability-sdk[tiktoken]"
```

The SDK bundles the OpenInference instrumentors but **not** the frameworks: it
instruments the LangChain/LlamaIndex/Ollama/Groq/ChromaDB versions your app
already has. A framework that is not installed is skipped silently.

## 4. Smoke test before touching code (5 minutes)

Prove the endpoint + key work by replaying the deterministic mock suite:

```bash
aiobs-mock --endpoint http://localhost:8000 --api-key <your-key>
```

Expected: `30/30 scenarios passed`, and ~30 executions appear in the dashboard
within seconds (including failures and one looped `loop_demo` execution). If
this step fails, fix it here — nothing below will work until it passes.

## 5. Step 1 — initialize once at process startup

```python
import ai_observability

ai_observability.init(
    service_name="checkout-agent",        # shows up in telemetry resources
    service_version="1.4.2",
    deployment_environment="prod",
    # capture_prompts=False,             # default: payloads never leave the app
    # loop_detection=True,               # default: measure repeated calls
)
```

Configuration is 12-factor: explicit `init()` arguments override environment
variables, so deployments usually keep the secret in the env:

| Variable | Meaning |
|---|---|
| `AI_OBSERVABILITY_API_KEY` | the ingest key (required for the platform) |
| `AI_OBSERVABILITY_ENDPOINT` | platform base URL (default `http://localhost:6006`, the local Phoenix) |
| `AI_OBSERVABILITY_LOOP_DETECTION` | `false` disables loop measurement entirely |
| `OTEL_SERVICE_NAME` / `OTEL_SERVICE_VERSION` / `OTEL_DEPLOYMENT_ENVIRONMENT` | resource identity |
| `AI_OBSERVABILITY_BACKFILL_TIKTOKEN` | `1` to estimate missing token counts with tiktoken |

Rules of thumb:

- call `init()` **early** — before you create chat clients/agents (the raw
  Ollama/Groq/ChromaDB interceptors must be in place before the first call);
- `init()` is safe: it never raises into your app, unknown arguments raise a
  `TypeError` (typo protection), and re-initializing logs a warning;
- `project_id` / `AI_OBSERVABILITY_PROJECT_ID` exists for legacy/Phoenix
  routing only — **the key identifies the project**, leave it unset.

## 6. Step 2 — wrap the entry point in a workflow

`workflow()` is the unit the dashboard calls an execution. Both forms work
(sync + async alike):

```python
from ai_observability import workflow

# decorator
@workflow(name="checkout", workflow_id="order-123", version="v2",
          context={"channel": "web", "tenant": "acme"})
def handle_order(order_id: str) -> str:
    ...

# or context manager where you already have the entry point
def handle_order(order_id: str) -> str:
    with workflow(name="checkout", workflow_id=order_id, version="v2",
                  context={"channel": "web"}):
        ...
```

- `name` — the workflow name shown in the dashboard (required).
- `workflow_id` — a *stable* id for one logical run. Pass your own (order id,
  session id, LangGraph `thread_id`): retries, HITL interrupt/resume, or a
  later re-run of the same id join the same trace. Omit it and every top-level
  `workflow()` gets a fresh trace (see “One run is not automatically one
  execution” below).
- `version`, `context` — displayed on the execution, searchable; keep
  business metadata here (it is redacted for secrets before storage).
- `capture_prompts=True` on one workflow opts that run into payload capture —
  handy for debugging a specific tenant without touching global config.
- Workflows nest: an inner `workflow()` becomes a child span, not a new
  execution.

### One run is not automatically one execution

The dashboard groups spans by **trace**: normally one root span plus everything
under it. It has no separate notion of your app's "run", so every top-level
`workflow()` is a new execution. Two patterns show up in real integrations:

1. **One workflow per stage.** A pipeline that opens
   `workflow(name="document-extraction")` for each document, then
   `workflow(name="grounded-answer")` for the answer, produces one execution
   per stage. A KEDB query hit this: two `coordinator.search_port` roots plus
   one `grounded-answer` root, three executions for one request.

2. **A span emitted off-thread.** Raw clients (Ollama/Groq/ChromaDB) and
   manual spans use the OTel context of the thread they run on. If you
   dispatch the call to a plain `ThreadPoolExecutor` or `threading.Thread`,
   that context is not inherited, so the span has no parent and starts a new
   trace. An onboarding run showed this: the `document-extraction` workflow
   root was present, but the OCR `Chat` call inside it was exported as a
   separate root.

Keep one logical run in one execution by opening a single outer workflow and
letting stages nest:

```python
def handle(request_id: str, documents: list[Document]) -> str:
    with workflow(name="onboarding", workflow_id=request_id):
        for doc in documents:
            with workflow(name="document-extraction", context={"file": doc.name}):
                ocr(doc)                 # nested, same trace
        return answer(...)               # nested, same trace
```

If a stage is only a step and should never be its own execution, use
`span(...)` instead of `workflow(...)` — but it still needs an enclosing
workflow, otherwise it is a root too.

For calls that really run on another thread, carry the context over (with
OTel's default contextvars-based context):

```python
import contextvars

ctx = contextvars.copy_context()
executor.submit(ctx.run, ocr, path)
```

If the stages live in separate processes or hosts, give every top-level
`workflow()` the **same `workflow_id`** (your request id). The SDK derives the
trace id from that seed, so the roots join one trace. The trace will contain
multiple root spans — the platform supports that (it is how LangGraph
interrupt/resume already works) — but an outer workflow is cleaner because the
execution is named after the real entry point and renders as one tree.

Long-running services: one `init()` at startup and a `workflow()` per request
(FastAPI middleware, request handler, job runner — thin wrappers are fine).

## 7. Step 3 — nothing else for instrumented frameworks

Inside a workflow, framework calls are captured automatically and nest under
it:

| In your app | Captured as |
|---|---|
| LangChain / LangGraph (agents, chains, tools, prompts) | AGENT/CHAIN/LLM/TOOL spans; LangGraph nodes traced; HITL interrupts also captured |
| LlamaIndex (indexes, retrievers, query engines) | CHAIN/RETRIEVER/LLM spans |
| Raw `ollama` client, raw `groq` client | LLM spans with token counts and errors |
| Raw `chromadb` client (`collection.query`) | RETRIEVER span with documents |

Raw Ollama/Groq calls made from a LangChain chat model (`ChatOllama` /
`ChatGroq`) are not double-traced: the LangChain LLM span wins, so calls,
tokens and cost are counted once.

For anything else — your own steps, validation, queue hops, business logic —
use the manual span helper (sync/async context manager or decorator):

```python
from ai_observability import span

@span(name="validate_output", context={"checks": 3})
def validate(result): ...

with span("charge_card", context={"amount": 42}):
    charge()
```

Exceptions on any span are recorded, classified by the backend, and propagate
to the workflow root status — do not swallow them inside the workflow if you
want the failure visible. Framework **interrupts** (LangGraph HITL) are not
failures; they are captured as `sdk.hitl.*` data instead.

## 8. Step 4 — verify and shut down cleanly

The SDK never blocks or raises on telemetry problems; make export health
visible instead:

```python
ok = ai_observability.flush(timeout_millis=5000)   # False = not delivered
stats = ai_observability.export_stats()            # batches exported/failed, last error
```

- Scripts/jobs: `flush()` (or nothing at all — an atexit flush is registered)
  before you exit.
- Servers: `ai_observability.shutdown()` on app stop (flushes + uninstruments).
- If `stats["failed_batches"]` climbs: wrong endpoint, revoked key, or
  network; check `stats["last_error"]`.

Expected dashboard result after your first real run: the execution appears in
**Engineering** with status, duration, tokens, cost and its span tree; failures
get a kind; repeated identical tool calls get the `loop` badge and feed the
`Looped executions` alert metric.

## 9. Privacy and data handling (defaults, worth knowing)

- **Prompts/responses are not captured** unless `capture_prompts=True`
  (globally or per workflow). Payload keys are stripped at the SDK boundary
  before export.
- **Loop detection is content-free**: the SDK exports a salted hash
  (`sdk.call.sig`) per LLM/TOOL call for repeat detection; the salt is
  per-process and never exported, so the hash is only meaningful for equality
  within that run. Disable with `loop_detection=False` if you do not want it.
- Business `context`/`metadata` is stored redacted (password/secret/token/…).
- Retention is an operator setting (`AIOBS_RETENTION_DAYS`); purge is the
  supported deletion mechanism.

## 10. Troubleshooting checklist

| Symptom | Likely cause |
|---|---|
| No executions appear | endpoint points at Phoenix (`:6006`) instead of the platform; wrong/rotated key; app exits before export (call `flush()`) |
| Executions appear without cost | model not in the pricing table — shows `*`/“unpriced”; ask an admin to add pricing |
| Execution shows no prompts | expected: capture is opt-in (`capture_prompts=True`) |
| Two or more executions instead of one | `workflow()` opened once per stage or retry for one logical run — open one outer workflow, or reuse `workflow_id` (see §6) |
| An extra execution rooted at an LLM/RETRIEVER span | the call ran on a thread without the active context — propagate context (e.g. `copy_context().run`) or keep it inside the workflow |
| Two concurrent LLM spans with the same model/tokens | old SDK double-instrumented `ChatOllama`/`ChatGroq` + the raw client — upgrade to SDK **0.3.1+** |
| Duplicated spans/`warn: already instrumented` | another OpenInference/Arize instrumentor is active for the same framework — keep only one |
| `loop` badge on a healthy-looking run | the run repeated identical calls (same tool+args or same LLM input ≥3×, or a repeating 2–4 step cycle) — inspect the execution's loop panel |
| Export errors in logs | check `export_stats()["last_error"]`; 401 = bad key, 409 = conflicting project header |

## 11. Minimal end-to-end example

```python
import ai_observability
from ai_observability import span, workflow

ai_observability.init(service_name="my-agent")  # key + endpoint from env


@span(name="validate")
def validate(question: str) -> str:
    return question.strip()


@workflow(name="support-agent", version="v1", context={"channel": "cli"})
def answer(question: str) -> str:
    question = validate(question)
    return agent.invoke(question)  # LangChain/LlamaIndex/etc. — auto-traced


if __name__ == "__main__":
    print(answer("Where is my order?"))
    ai_observability.shutdown()
```

More material to copy from:

- `sdk/README.md` — full SDK surface, per-framework notes, LangGraph HITL.
- `sdk/examples/` — real-provider demos (checkout agent, RAG variants,
  LangGraph refund approval) with per-provider setup.
- `aiobs-mock --scenario loop_tool_repeat` — see the loop badge end to end
  against your own endpoint/key.
