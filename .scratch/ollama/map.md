# Ollama Raw-Client Support Map

## Destination

First-class raw **Ollama client** support in the SDK (`sdk/`): apps that call
`ollama.chat(...)` directly (no LangChain/LlamaIndex wrapper) get OpenInference
LLM spans — provider, model, token counts, messages, errors, streaming — nested
under the manual workflow root, with local models priced at $0 in the backend.
The map is complete when the wiring, tests, scenarios, pricing row, and plan
updates are in place, with every decision below resolved.

## Notes

- Domain: AI observability / agentic monitoring. The SDK already reuses
  `openinference-instrumentation-langchain` and `-llama-index`; this effort
  adds `openinference-instrumentation-ollama` (v0.1.9, Arize) the same way.
- Motivating app: `andrei5amabil/OnboardingFulfillment` — FastAPI + LangGraph
  with plain `ollama.chat()` calls (JSON-schema constrained output, manual
  token counts), verified during planning on 2026-09-30.
- Upstream facts (verified against the installed wheel): instruments
  `ollama.chat` / `Client.chat` / `AsyncClient.chat` (streaming included) as
  OpenInference LLM spans; `llm.provider = "ollama"` and `llm.model_name` are
  recorded request-side (so errored calls carry them); token counts from
  `prompt_eval_count`/`eval_count`; errors as exception events + ERROR status;
  `generate` / `embed` are **not** instrumented.
- The instrumentor must be active before the first chat call (the module-level
  `ollama.chat` helper is re-bound at instrument time).
- Skills: task tickets only — the approach was settled with the user (option 1:
  wire the instrumentor into the SDK; add zero-rate local pricing).

## Decisions so far

- [Ollama instrumentation](issues/01-ollama-instrumentation.md): reuse
  `openinference-instrumentation-ollama>=0.1.9`; `chat`-only coverage; `ollama`
  is a dev dependency only (the instrumentor hides it behind its `instruments`
  extra); skip silently when absent; no ADR (follows the established
  reuse-instrumentors pattern).
- [Ollama wiring](issues/02-ollama-wiring.md): `_instrumentation.py` gains
  `_instrument_ollama` / `_already_instrumented_ollama` / availability guard,
  mirroring the LangChain/LlamaIndex blocks; `uninstrument()` restores the raw
  client. **Unified afterwards**: all three instrumentors skip a missing
  framework at debug level and run through `_safe_instrument()`, so failures
  never escape `init()` (plan §8).
- [Ollama tests](issues/03-ollama-tests.md): offline tests patch the HTTP
  boundary (`Client._request`) to scripted `ChatResponse`s; scenarios
  `oll_chat`, `oll_chat_error`, `oll_chat_redacted`, `oll_chat_stream`.
- [Assemble the Ollama plan](issues/04-assemble-ollama-plan.md): update
  `plans/sdk.md` (§2, §7.4, §9.2, §10, §12), `plans/backend.md` §8.1,
  `plans/implementation-plan.md` (§5, §8), and `sdk/README.md`.
- [Ollama pricing](issues/05-ollama-pricing.md): seed a zero-rate
  `("ollama", "*", "default")` row so local models price at $0.00 instead of
  "unpriced" (explicit price, not a fabricated one; backend decision 03 holds).

## Not yet specified

- OnboardingFulfillment-side integration (`init()` + `workflow(workflow_id=...)`
  wrapping) — lives in that repo.
- Remote/hosted Ollama behind a proxy: the same zero-rate default would price
  it at $0; a real pricing row would be needed if usage is billed.

## Out of scope

- Upstream coverage for `generate` / `embed` (not instrumented by the OpenInference
  package); OpenAI/Anthropic raw-client instrumentation (still deferred).
- Re-instrumenting Ollama spans in the SDK (reuse the official instrumentor).
- Changes to the app being monitored (OnboardingFulfillment).
