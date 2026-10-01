# 01 — Groq instrumentation

Type: task
Status: resolved
Blocked by: —

## Goal

Decide how raw `groq` Python client calls become LLM spans in the SDK:
reuse an existing OpenInference instrumentor or build custom tracing.

## Decision

Reuse **`openinference-instrumentation-groq`** (v0.1.30, Apache-2.0) with the
SDK-owned TracerProvider — the same pattern as LangChain/LlamaIndex/Ollama; no
custom tracing. The instrumentor patches
`groq.resources.chat.completions.Completions.create` (sync) and
`AsyncCompletions.create`.

- **Coverage**: non-streaming `chat.completions.create` → OpenInference **LLM**
  spans named `Completions` with input messages + `input.value`,
  `llm.invocation_parameters`, and `llm.provider = "groq"` request-side; model,
  token counts, output messages and `output.value` response-side; errors as
  exception events + ERROR status (re-raised unchanged).
- **Errored spans**: the request side does not record `llm.model_name` (unlike
  Ollama) — provider + invocation parameters only; documented, not worked
  around. `groq.RateLimitError` classifies as `rate_limit` via the shared
  hint patterns.
- **Streaming**: verified against a fake SSE transport — one span, OK, but the
  streamed content/usage is not accumulated (`output.value` is the stream
  object repr). The motivating app does not stream; no scenario, documented
  as an upstream gap.
- **Dependency shape**: `groq` sits in the instrumentor's `instruments` extra,
  so the SDK adds it to the **dev** group only; the raw client stays optional
  at runtime.
- **Absent client**: `init()` skips Groq instrumentation silently (debug log).
- **No ADR**: extends the settled "reuse OpenInference instrumentors" pattern
  (`.scratch/sdk/issues/05`, `06`).

## Comments

Verified while writing the offline fakes: `Groq(..., http_client=...)` accepts
an `httpx.Client`, so `httpx.MockTransport` can script responses end-to-end
through the real client and instrumentor; a 429 JSON body raises the real
`groq.RateLimitError`.
