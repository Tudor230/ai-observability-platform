# Retry observability research

Type: research
Status: resolved
Blocked by:

## Question

How do retries surface to instrumentation in v1 targets: LangChain `with_retry`, LlamaIndex retry behavior, and OpenAI/Anthropic client retries (max_retries)? What signals exist (attempt counts, provider status codes, framework hooks, events) that an SDK could capture without double-instrumenting provider SDKs (OpenInference issue #2268)? Recommend the concrete observation points for an SDK-side `sdk.retry.count` / `sdk.retry.of` attribute scheme.

## Answer

Resolved by research subagent; full findings with sources: `.scratch/sdk/research/09-retry-observability.md`.

- **LangChain `with_retry()`**: each attempt re-fires callbacks with the same run_id; attempts ≥ 2 carry a `retry:attempt:N` tag; failed attempts fire `on_*_error`. Result on traces: repeated sibling ERROR LLM spans (retries inferable), but the OpenInference tracer ignores tags/events — nothing labeled.
- `on_retry` callback (tenacity RetryCallState) fires only for `create_base_retry_decorator` providers (mistralai, vertexai, community) — not openai/anthropic.
- `llm.invocation_parameters` includes `max_retries` for ChatAnthropic (verified) but NOT ChatOpenAI (OpenAI passes it only to the client).
- **LlamaIndex**: retries (tenacity decorator + client max_retries) happen inside a single `CBEventType.LLM` event — zero callback signal; `max_retries` excluded from payloads.
- **OpenAI/Anthropic clients**: no first-party retry hooks (openai issue #1190); retries on 408/409/429/5xx/connection errors, `max_retries` default 2. Only hook: an injected `httpx.Client(event_hooks=...)` via `http_client=`, which works in both SDKs and both frameworks.
- **Conventions**: neither OpenInference nor OTel GenAI semconv defines retry/attempt attributes.
- **Not observable without framework changes**: actual provider-client attempt counts via the instrumentors, ChatOpenAI max_retries in spans, LlamaIndex retry budget, `retry:attempt:N` tags.
- **Recommended v1** (adopted in ticket 04): `sdk.retry.of` from `llm.invocation_parameters` where present; `sdk.retry.count` via an SDK-owned SpanProcessor counting failed-attempt sibling LLM spans when the workflow root ends; opt-in httpx event-hook client for exact counts documented as future work.