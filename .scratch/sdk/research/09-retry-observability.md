# Retry Observability Research — Findings

Research ticket: `.scratch/sdk/issues/09-retry-observability.md`
Date: 2026-08-29
Scope: Can our SDK capture LLM retries (attempt counts, `sdk.retry.count` / `sdk.retry.of`) through the official LangChain / LlamaIndex OpenInference instrumentors and the OpenAI/Anthropic Python clients, without instrumenting provider SDKs directly? What are the minimal, honest observation points for v1?

Method: source-level inspection of `langchain_core`, `langchain-openai`, `langchain-anthropic`, `llama-index-core`, `llama-index-llms-openai`, `openai-python`, `anthropic-sdk-python`, the OpenInference Python instrumentors, and OTel GenAI semconv; plus **empirical verification** of `_get_invocation_params()` and `RunnableRetry` callback behavior against installed packages (langchain-openai 0.3.x, langchain-anthropic, langchain-core 1.x, as of 2026-08-29).

---

## TL;DR

- **Retry budgets are partially observable, actual attempt counts are almost never observable** through the standard instrumentor paths. No framework surfaces per-attempt data on the successful span.
- **LangChain**: `with_retry()` re-fires callbacks with the *same run_id* per attempt; attempts ≥ 2 carry tag `retry:attempt:N`; failed attempts produce `on_*_error` on that run_id. The OpenInference tracer ignores tags and events, so the *artifact* is repeated sibling ERROR spans (one per failed attempt) — retries are *inferred* by counting error spans, never labeled. `llm.invocation_parameters` contains `max_retries` for `ChatAnthropic` (verified) but **not** for `ChatOpenAI` (verified).
- **LlamaIndex**: retries (tenacity `@llm_retry_decorator` + client-side `max_retries`) happen *inside* a single `CBEventType.LLM` callback event — zero retry signal to the callback system. `EventPayload.SERIALIZED` (= `to_payload()` = LLM metadata) does not include `max_retries`; the OpenInference callback's `_extract_invocation_parameters` keeps only `additional_kwargs` + `temperature` + `max_tokens`.
- **OpenAI/Anthropic clients**: no first-party retry hooks (openai-python issue #1190 open since 2024, maintainer's own suggestion: httpx `event_hooks`). The only clean attempt-level hooks are (a) injected custom `httpx.Client(event_hooks=...)` via `http_client=` (works in both SDKs, in LangChain and LlamaIndex integrations), and (b) their debug logs (`"Retrying request in X seconds"`).
- **Conventions**: neither OpenInference nor OTel GenAI semconv define any retry/attempt attribute. OTel GenAI has `error.type` (stable) for error classification only. No open OpenInference issue proposes retry attributes.
- **Recommendation**: v1 = (1) read `max_retries` where it exists in `llm.invocation_parameters` (LangChain+Anthropic) as `sdk.retry.of`; (2) count failed-attempt sibling LLM spans at parent-span end via an SDK-owned `SpanProcessor` (the SDK controls the provider/export pipeline) to derive `sdk.retry.count`; (3) offer an opt-in SDK-provided httpx client with event hooks for exact per-call attempt counts in direct-client or framework `http_client=` slots; (4) treat `with_retry`/LlamaIndex/provider-client retries as "attempts visible only as repeated error spans" and document them as such.

---

## 1. LangChain retry mechanisms and tracing signals

There are **three distinct retry layers**, with very different observability:

### 1.1 `RunnableRetry` / `.with_retry()` (tenacity, any Runnable)

Source: `langchain_core/runnables/retry.py` — https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/runnables/retry.py ; docs https://reference.langchain.com/python/langchain-core/runnables/retry/RunnableRetry

- `with_retry(retry_if_exception_type=(Exception,), wait_exponential_jitter=True, stop_after_attempt=3)` → `RunnableRetry` (`max_attempt_number` default 3). Retries on **any** exception by default.
- Implementation: each attempt re-invokes the bound runnable with a patched config:
  `_patch_config` (retry.py:159-166): `attempt = retry_state.attempt_number; tag = f"retry:attempt:{attempt}" if attempt > 1 else None; return patch_config(config, callbacks=run_manager.get_child(tag))`
- **Empirically verified** (probe callback on `RunnableLambda(...).with_retry(stop_after_attempt=3)`): every attempt fires `on_chain_start` **with the same run_id**; attempts 2 and 3 carry `tags=['retry:attempt:2']` / `['retry:attempt:3']`; every failed attempt fires `on_chain_error` on that run_id. **No `on_retry` callback is fired** by `with_retry`.
- Consequences for tracing (incl. the OpenInference instrumentor): one retried call = one run_id = one span *per attempt* (sibling spans), failed attempts = ERROR status + `exception.*` events (via `on_*_error` → `_record_exception`), final attempt OK. The retry tags are **ignored** by the OpenInference tracer (it never reads `run.tags` — grep of `_tracer.py` for tags/retry finds nothing). So `with_retry` shows up as repeated error spans with no retry labeling.

### 1.2 Provider-client retries (OpenAI / Anthropic integrations)

- `langchain-openai` `ChatOpenAI`: `max_retries` is a pydantic field (chat_models/base.py:838), passed **only** into the `openai.OpenAI(max_retries=...)` client at construction (base.py:1371-1372). No tenacity decorator anymore. Retries happen inside the OpenAI client, invisible to LangChain callbacks.
- `langchain-anthropic` `ChatAnthropic`: same pattern — `max_retries` (default 2) → `anthropic.Client(max_retries=...)` (`_client_params`, chat_models.py:1355-1362). No callback signal.
- **Not observable at the LangChain layer** for these two providers.

### 1.3 Tenacity decorators in legacy/other providers → `on_retry` callback

Source: `langchain_core/language_models/llms.py:77-132` (`create_base_retry_decorator`) — https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/language_models/llms.py

- `create_base_retry_decorator(error_types, max_retries, run_manager)` builds a tenacity `retry(...)` with `before_sleep=_before_sleep`, and `_before_sleep` calls **`run_manager.on_retry(retry_state)`** (sync) / schedules it (async).
- `on_retry` is a **first-class callback** on `BaseCallbackHandler` (langchain_core/callbacks/base.py:455) receiving tenacity's `RetryCallState` (`attempt_number`, `idle_for`, `outcome`, exception), plus `run_id` / `parent_run_id`.
- `BaseTracer.on_retry` (langchain_core/tracers/base.py:185) appends a `{"name": "retry", "kwargs": {"slept", "attempt", "outcome", "exception", "exception_type"}}` event to `run.events` (`_TracerCore._llm_run_with_retry_event`, langchain_core/tracers/core.py:291).
- **Who still uses it**: `langchain-mistralai` (`completion_with_retry`/`acompletion_with_retry`, chat_models.py — retries only `httpx.RequestError`/`httpx.StreamError`), `langchain-google-vertexai` (`_retry.py`), various `langchain-community` models. NOT langchain-openai/anthropic.

### 1.4 What `openinference-instrumentation-langchain` captures

`_tracer.py` (main, ~v0.1.7x): https://github.com/Arize-ai/openinference/blob/main/python/instrumentation/openinference-instrumentation-langchain/src/openinference/instrumentation/langchain/_tracer.py

- **No retry handling at all**: no `on_retry` override (inherits `BaseTracer.on_retry` — so a `retry` event *is* appended to `run.events` for tenacity providers, but the tracer never reads `run.events`), no tag handling (so `retry:attempt:N` is dropped), no attempt/retry attributes.
- `llm.invocation_parameters` = `run.extra["invocation_params"]` = `_get_invocation_params()` (`_tracer.py:1053-1064`). What that contains is provider-specific — see §1.5.
- Span status: `ERROR` + `run.error` as description when `run.error` set, else `OK` (`_update_span`, `_tracer.py:299-304`); exceptions recorded as events on `on_*_error` (and only if the span is still in `_spans_by_run` — for `with_retry`, each attempt gets its own span because `_end_trace` pops the span when the failed attempt ends).

### 1.5 Does `llm.invocation_parameters` capture `max_retries`? (empirically verified)

`BaseChatModel._get_invocation_params` (langchain_core/chat_models.py:1493) = `self._dict_for_compat()` + `stop` + kwargs, where `_dict_for_compat()` calls the langchain-deprecated `dict()` → `asdict()` (chat_models.py:2343-2355) = `dict(self._identifying_params)` + `_type`.

| Provider | `_identifying_params` | `max_retries` in `llm.invocation_parameters`? |
|---|---|---|
| `ChatOpenAI` | `{"model_name", **self._default_params}` (base.py:2205) | **NO** — `_default_params` excludes it (model request params only) |
| `ChatAnthropic` | `{model, max_tokens, temperature, top_k, top_p, model_kwargs, streaming, max_retries, default_request_timeout, thinking, output_config}` (chat_models.py:1360-1370) | **YES** — verified: `{'max_retries': 2, ...}` appears in `_get_invocation_params()` |

Verified on installed langchain-openai 0.3.x / langchain-anthropic: `ChatOpenAI(max_retries=2)._get_invocation_params()` → `{model, model_name, stream, temperature, max_completion_tokens, _type}` (no `max_retries`); `ChatAnthropic(max_retries=2)._get_invocation_params()` → includes `max_retries: 2`.

So: **LangChain+OpenAI retry budget is NOT in the emitted span data; LangChain+Anthropic retry budget IS** (`llm.invocation_parameters` JSON). Both are *configured budgets*, never actual attempt counts.

---

## 2. LlamaIndex retry behavior and callbacks

### 2.1 Retry layers

- `llama-index-llms-openai` `OpenAI` LLM: **two stacked retries, both inside one callback event**:
  1. `@llm_retry_decorator` (base.py:102-118) — tenacity, retries the whole `_chat`/`_stream_chat` on `(openai.APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)`; `max_retries` default **3**; backoff respects `Retry-After` header (`_WaitRetryAfter`, utils.py:323-357); `before_sleep=before_sleep_log` only.
  2. openai client `max_retries` — `OpenAI(max_retries=self.max_retries, http_client=...)` (`_get_credential_kwargs`, base.py:451-454).
- Call flow: public `chat()` → `@llm_chat_callback()` (emits `CBEventType.LLM`) → `self._chat()` → `@llm_retry_decorator` → client. **Retries occur inside a single LLM callback event; the callback system sees one start/end per logical call.** No retry payload exists in `EventPayload`.
- Other LlamaIndex components (agents, tools) do not add LLM retry semantics; agent/tool retry loops are app-level (separate LLM calls → separate events).

### 2.2 What the callback system / instrumentor exposes

- `CBEventType` has no retry event type; `BaseCallbackHandler` has no `on_retry` equivalent (LlamaIndex callbacks: `start_trace`, `on_event_start`, `on_event_end`, `end_trace` — https://developers.llamaindex.ai/python/framework-api-reference/callbacks).
- `EventPayload.SERIALIZED = _self.to_payload()` (llama_index/core/llms/callbacks.py:57) = `{"class_name", **metadata.model_dump()}` (llm.py:58-63) — **metadata only**; verified `OpenAI(model='gpt-4o', max_retries=5).to_payload()` has no `max_retries`. The docstring explicitly says it must never contain credentials; it also drops `max_retries`.
- `openinference-instrumentation-llama-index` `_callback.py` `_extract_invocation_parameters` (lines 186-197) copies only `additional_kwargs` + `temperature` + `max_tokens` into `llm.invocation_parameters` — no `max_retries`, no retry data.
- Errors: `EventPayload.EXCEPTION` → `record_exception` + status ERROR (same as before). Streaming wrapped so status set on stream error.
- The `max_retries` value is reachable only on the LLM **instance** (pydantic field, `llm.max_retries`, default 3) — e.g. via `Settings.llm` if the SDK can access it (not via callbacks).

### 2.3 New instrumentation module (span-based)

LlamaIndex's newer `llama_index.core.instrumentation` emits `LLMChatStartEvent/LLMChatEndEvent` etc. carrying `model_dict` (same `to_payload()` metadata) — no retry fields either. Not a retry source.

---

## 3. OpenAI / Anthropic Python clients

### 3.1 Retry semantics

- Both are httpx-based stainless/derived SDKs with identical machinery:
  - `openai`: `max_retries` (default `DEFAULT_MAX_RETRIES = 2`), client-level or per-request `client.with_options(max_retries=5)`; retry on connection errors, **408, 409, 429, ≥500**, plus `x-should-retry` response header (`_should_retry`, src/openai/_base_client.py:815-856).
  - `anthropic`: same shape (`_should_retry` on 408/409/429/≥500 + connection errors, `DEFAULT_MAX_RETRIES = 2`, `max_retries=None` raises, `math.inf` = unlimited) — src/anthropic/_base_client.py:821-856.
  - Backoff honors `Retry-After`; every retry logs `log.debug("Retrying due to status code %i")` and `log.info("Retrying request in %f seconds")` (logger `openai._base_client` / `anthropic._base_client`).

### 3.2 Telemetry / hooks around retries

- **No first-party retry callback or telemetry hook.** openai-python issue #1190 ("Provide a callback whenever retry is triggered", open since 2024) — maintainer: "I don't think we have a great way to do this right now… You could use httpx event_hooks". Never implemented.
- **Observable hooks an SDK can use (without instrumenting the client):**
  1. **httpx event hooks via injected client** — `OpenAI(http_client=httpx.Client(event_hooks={"request": [...], "response": [...]}))`, same for `Anthropic(http_client=...)`, and *both frameworks accept the same injection* (`ChatOpenAI(http_client=...)`, `OpenAI(llm, http_client=...)`). Each HTTP attempt fires one `request` + one `response` hook; a retry = multiple `response` events carrying retryable status codes (429/5xx). Count = responses seen − final successful/error response. Caveats: (a) openai-python is migrating to **httpx2** (`DefaultHttpx2Client`, see openai-python `httpx2.md`); (b) streaming responses need care reading `response.content` in hooks (consumes the stream); (c) this observes *HTTP attempts*, which include retries from BOTH layers (framework tenacity + client) — actually the desired signal.
  2. **Log-based observation** — attach a `logging.Handler` to `openai._base_client` / `anthropic._base_client`; retries are DEBUG/INFO lines with backoff seconds. Works today, fragile (private module, format may change).
- **Not exposed**: attempt count on the final response object, status-code history, or any `RetryError` wrapper (last error propagates unchanged).

---

## 4. OTel / OpenInference conventions for retries

- **OpenInference**: zero retry/attempt attributes in the spec (`spec/semantic_conventions.md`, `spec/llm_spans.md`). Only error representation is OTel-standard: span status + `exception.*` events. `tag.tags` is an OpenInference *context* attribute (set via `using_tag`) — unrelated to LangChain run tags, and the instrumentor does not map run tags onto spans anyway. No open issue proposing retry/attempt attributes (checked open issues, 2026-08-29).
- **OTel GenAI semconv** (experimental, `semantic-conventions-genai`): no retry/attempt attribute either. Error classification exists via the **stable core `error.type`** attribute (e.g. `timeout`, `500`, `context_length_exceeded`) on gen-ai spans and metrics — https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md ; metrics use `error.type` too (`gen_ai.client.operation.duration`). So the only standardized "retry-adjacent" signal is error typing; nothing encodes attempts.
- **Industry state**: Langfuse OTel mapping explicitly does not label retries ("structured output retries show up as multiple provider-call spans… you infer retries by counting spans", langfuse discussion 11612); LangSmith logs `max_retries` only as constructor kwargs metadata; Arize Phoenix has no retry field. Counting spans / error spans is the de-facto method. (The crewai instrumentor even warns that "provider- and retry-driven LLM span count variability" affects tests when both layers are instrumented — reinforcing that we must not double-instrument.)
- **`sdk.*` namespace**: no precedent in OTel/OpenInference; our `sdk.retry.count` / `sdk.retry.of` namespacing is free of collisions with existing conventions. (OpenInference context API `using_attributes` allows arbitrary custom attributes on instrumentor-created spans — the LangChain tracer applies `get_attributes_from_context()` at span start, `_tracer.py:311`; LlamaIndex callback likewise merges context attributes.)

---

## 5. Recommendation: concrete v1 observation points

### What IS observable per stack (summary table)

| Signal | LangChain | LlamaIndex | OpenAI/Anthropic direct |
|---|---|---|---|
| `max_retries` (configured budget) | ✅ Anthropic via `llm.invocation_parameters`; ❌ OpenAI (not emitted) | ❌ via spans; ✅ only on LLM instance (`Settings.llm.max_retries`) if SDK can reach it | ✅ `client.max_retries` |
| Actual attempt count, retries by `with_retry` | ⚠️ Inferable: repeated sibling ERROR LLM spans (one per failed attempt) for the same run; `retry:attempt:N` tag exists on attempts ≥2 but is **dropped** by the instrumentor | ❌ hidden inside one `CBEventType.LLM` event | ⚠️ via injected httpx `event_hooks` (per-attempt request/response) or debug logs |
| Actual attempt count, provider-client retries (openai/anthropic) | ❌ invisible (inside client) | ❌ invisible (inside client) | ⚠️ same httpx hooks / logs |
| tenacity retries (`create_base_retry_decorator` providers: mistralai, vertexai, community) | ✅ `on_retry` callback → `RetryCallState(attempt_number, outcome, exception)`; BaseTracer appends `{"name":"retry","kwargs":{...}}` to `run.events`; ❌ not surfaced by the OpenInference tracer | n/a | n/a |
| Errors per attempt | ✅ `exception.*` events + ERROR status on failed-attempt spans | ✅ `EventPayload.EXCEPTION` on the single LLM event (final error only) | ✅ exceptions (final error only) |

### Recommended mechanism (no framework changes, no double instrumentation)

1. **`sdk.retry.of` (budget)** — read `max_retries` from the *already-emitted* `llm.invocation_parameters` span attribute (LangChain+Anthropic; reliable). For LangChain+OpenAI and LlamaIndex, do not fabricate: leave unset in v1 and document (or, if the SDK's own `span()` helper wraps user-supplied model objects, read `.max_retries` from the instance where reachable — best-effort, per-version).
2. **`sdk.retry.count` (actual attempts)** — SDK-owned **`SpanProcessor`** in its own export pipeline (the SDK already owns TracerProvider + BatchSpanProcessor + OTLP exporter, per ticket 03): buffer LLM spans; when their parent span ends (CHAIN/AGENT/workflow span — the SDK knows these), count same-parent, same-name ERROR sibling LLM spans (+ exception events) as retried attempts for the successful sibling, and stamp `sdk.retry.count` / `sdk.retry.of` on the parent span (or final LLM span) **before** handoff to the exporter. This captures the `with_retry` case exactly as it manifests in the OpenInference data model, and adds zero framework coupling. It does NOT capture provider-client-internal retries (no artifact exists for them).
3. **Opt-in exact attempts (v2-ish, cheap now)**: SDK ships a helper that builds a `httpx.Client`/`AsyncClient` with retry-counting `event_hooks`, injectable at `ChatOpenAI(http_client=...)`, `OpenAI(http_client=...)`, `Anthropic(http_client=...)`, or `llama_index.llms.openai.OpenAI(http_client=...)`. Counts HTTP attempts per logical call and propagates via `using_attributes` context (or SDK span helper). No provider instrumentation, no span duplication, no streaming token miscounts — hooks observe transport, not SDK internals. This is the **only** exact per-call attempt signal for OpenAI/Anthropic. Note httpx2 migration risk in openai-python.
4. **Do not** wrap/observe via the LangChain `on_retry` callback in v1 — it only exists for tenacity-based providers (mistralai/vertexai/community), requires SDK callbacks to be threaded into user configs, and overlaps with the span-counting approach.

### What is NOT observable without framework changes

- Exact provider-client retry attempts for OpenAI/Anthropic through the standard instrumentor path (nothing in `Run`, `EventPayload`, or span attributes distinguishes them).
- `max_retries` for LangChain+OpenAI in emitted spans (would need an OpenInference/LangChain change to include client params in `_get_invocation_params`).
- LlamaIndex retry budget in spans (would need `to_payload()` to include it or the callback to copy more keys).
- `retry:attempt:N` tags → spans (would need the LangChain instrumentor to read `run.tags` — a small, natural upstream PR; same for reading `run.events` `retry` entries).
- Per-attempt attribution of token usage/cost: failed attempts that consumed tokens (rare on 429/5xx) leave no usage record in the final span.

### Impact on the SDK plan (ticket 02 trace model)

- `sdk.retry.*` attributes belong on the **LLM span** (or, when attempts span siblings, the enclosing CHAIN/AGENT/workflow span) — consistent with the backend consuming `sdk.*` attributes; add to the attribute dictionary in `plans/sdk.md`.
- Backend can also derive a conservative retry indicator from ERROR-status sibling spans, independent of SDK attributes.
- Reconfirm the #2268 constraint: never add provider-client instrumentation to close the retry gap — the httpx-hook approach is the sanctioned alternative.

---

## Source URLs (key)

- LangChain `RunnableRetry`/`with_retry`: https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/runnables/retry.py ; https://reference.langchain.com/python/langchain-core/runnables/retry/RunnableRetry
- `create_base_retry_decorator` + `on_retry`: https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/language_models/llms.py#L77 ; https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/callbacks/base.py#L455 ; `BaseTracer.on_retry` https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/tracers/base.py#L185 ; `_llm_run_with_retry_event` https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/tracers/core.py#L291
- `_get_invocation_params`: https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/language_models/chat_models.py#L1493 ; langchain-openai https://github.com/langchain-ai/langchain/blob/master/libs/partners/openai/langchain_openai/chat_models/base.py#L2207 ; langchain-anthropic https://github.com/langchain-ai/langchain/blob/master/libs/partners/anthropic/langchain_anthropic/chat_models.py (max_retries in `_identifying_params`)
- OpenInference LangChain tracer: https://github.com/Arize-ai/openinference/blob/main/python/instrumentation/openinference-instrumentation-langchain/src/openinference/instrumentation/langchain/_tracer.py
- LlamaIndex callbacks: https://developers.llamaindex.ai/python/framework-api-reference/callbacks ; `llm_chat_callback`/`to_payload` https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/llms/callbacks.py ; OpenAI LLM retries https://github.com/run-llama/llama_index/blob/main/llama-index-integrations/llms/llama-index-llms-openai/llama_index/llms/openai/base.py (llm_retry_decorator) and `utils.py` (`create_retry_decorator`)
- OpenInference LlamaIndex callback: https://github.com/Arize-ai/openinference/blob/main/python/instrumentation/openinference-instrumentation-llama-index/src/openinference/instrumentation/llama_index/_callback.py
- OpenAI client retries: https://github.com/openai/openai-python/blob/main/src/openai/_base_client.py (`_should_retry` ~L815); retry callback request https://github.com/openai/openai-python/issues/1190 ; httpx event-hook injection https://til.simonwillison.net/httpx/openai-log-requests-responses ; httpx2 migration https://github.com/openai/openai-python/blob/main/httpx2.md
- Anthropic client retries: https://github.com/anthropics/anthropic-sdk-python/blob/main/src/anthropic/_base_client.py (`_should_retry` ~L821)
- OTel GenAI semconv (error.type, no retry attr): https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md
- OpenInference spec (no retry attr): https://github.com/Arize-ai/openinference/blob/main/spec/semantic_conventions.md ; https://arize-ai.github.io/openinference/spec/llm_spans.html
- Langfuse on retry spans: https://github.com/orgs/langfuse/discussions/11612
- Double-instrumentation pitfall (nested spans / streaming token miscounts): https://github.com/Arize-ai/openinference/issues/2268