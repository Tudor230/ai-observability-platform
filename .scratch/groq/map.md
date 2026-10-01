# Groq Raw-Client Support Map

## Destination

First-class raw **Groq SDK** support in the SDK (`sdk/`): apps that call
`Groq().chat.completions.create(...)` directly get OpenInference LLM spans —
provider, model, token counts, messages, errors — nested under the manual
workflow root, with the gpt-oss models priced at Groq's published rates in the
backend. The map is complete when the wiring, tests, scenarios, pricing rows,
and plan updates are in place, with every decision below resolved.

## Notes

- Domain: AI observability / agentic monitoring. The SDK already reuses
  `openinference-instrumentation-ollama`; this effort adds
  `openinference-instrumentation-groq` (v0.1.30, Arize) the same way.
- Motivating app: `cristivalea/root-cause-analysis` — FastAPI + Streamlit +
  LangGraph with raw `Groq().chat.completions.create(...)` calls (JSON-schema
  constrained output, manual 429 retry loop), verified 2026-10-01.
- Upstream facts (verified against the installed wheel + a fake HTTP
  transport): wraps `groq.resources.chat.completions.Completions.create` and
  `AsyncCompletions.create`; `llm.provider = "groq"` and the input messages are
  request-side, `llm.model_name` / `llm.token_count.*` / output messages are
  response-side; errors as exception events + ERROR status. `stream=True`
  yields one span but the streamed content/usage is not accumulated (the span
  output is the stream object repr).
- `groq` is the instrumentor's `instruments` extra: dev dependency only;
  skip silently when absent (the Ollama/ChromaDB policy, plan §8).
- Skills: task tickets only — the approach extends the settled
  reuse-instrumentors pattern; no ADR.

## Decisions so far

- [Groq instrumentation](issues/01-groq-instrumentation.md): reuse
  `openinference-instrumentation-groq>=0.1.30`; non-streaming completions
  (sync + async); streaming documented as not accumulated; `groq>=0.9` dev
  dep; skip quietly when absent.
- [Groq wiring & tests](issues/02-groq-wiring-and-tests.md): `_instrumentation.py`
  gains `_instrument_groq` / `_already_instrumented_groq` / availability guard
  mirroring Ollama; fakes replace the HTTP boundary with `httpx.MockTransport`;
  scenarios `groq_chat`, `groq_chat_error`, `groq_redacted`.
- [Groq pricing & docs](issues/03-groq-pricing-and-docs.md): seed exact list
  rates for `openai/gpt-oss-120b` / `openai/gpt-oss-20b` — hosted provider, so
  **no** zero-rate row (unlike local Ollama); plans/README updates.

## Not yet specified

- Root-cause-analysis-side integration (`init()` + `workflow(workflow_id=...)`
  wrapping) — lives in that repo.
- Groq streaming accumulation upstream: if OpenInference later reconstructs
  stream output, add a `groq_chat_stream` scenario.

## Out of scope

- Custom Groq tracing (reuse the official instrumentor).
- OpenAI/Anthropic raw-client instrumentation (still deferred).
- Changes to the app being monitored (root-cause-analysis).
