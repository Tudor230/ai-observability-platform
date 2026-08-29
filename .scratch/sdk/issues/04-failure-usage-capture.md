# Failure & usage capture schema

Type: grilling
Status: resolved
Blocked by: 01, 02

## Question

Exactly what does the SDK record so the backend can classify failures and compute costs: error type/status/attributes, span statuses, token & usage counts, model, provider? How does opt-in prompt/response capture attach to spans?

## Answer

Decided by grilling with the user, informed by tickets 01 and 09.

- **Error capture**: rely on the instrumentors' exception events + ERROR span status, plus SDK namespaced attributes — `sdk.error.type` (exception class), `sdk.error.message` — on the failing span; the span kind identifies the failing layer (LLM/TOOL/RETRIEVER/CHAIN).
- **Classification hints**: raw facts + best-effort `sdk.error.kind` where cheaply detectable at capture time (timeouts via duration/status, rate limits where provider status is visible, invalid JSON via output checks). The backend holds the authoritative failure taxonomy.
- **Token usage**: SDK validates `llm.token_count.prompt/completion` (+ cache/reasoning details) exist on every LLM span, sanity-checks totals, and backfills missing counts (tiktoken/character-estimate chain). No `llm.cost.*` emission — Phoenix computes money server-side.
- **Provider accuracy**: SDK ships a small provider-normalization map and fills `llm.provider` when the LangChain instrumentor left it unset (deepseek, fireworks, xai, perplexity, huggingface, ...).
- **Prompt/response capture**: opt-in — global `init(capture_prompts=False)` default off, per-workflow override; when enabled, `TraceConfig` keeps payloads (messages, inputs/outputs) on LLM/TOOL/RETRIEVER spans.
- **Retries (required v1)**: `sdk.retry.of` from `llm.invocation_parameters` where frameworks expose `max_retries` (LangChain/Anthropic); `sdk.retry.count` via an SDK-owned SpanProcessor that counts failed-attempt sibling LLM spans when the workflow root ends. Exact per-attempt counts via an opt-in httpx event-hook client — future work. Mechanism researched in ticket 09.
- **Root propagation**: the workflow root span gets ERROR status when any descendant failed, plus a summary attribute (`sdk.error.kind` of the first/primary failure) — "workflow #123 FAILED" visible at a glance.