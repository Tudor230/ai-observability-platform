# 04 — Assemble the Ollama plan

Type: task
Status: resolved
Blocked by: 02, 03, 05

## Goal

Reflect raw-Ollama support in the plans and the SDK README.

## Changes

- `plans/sdk.md`
  - §2 Scope: instrumentor reuse line now covers LangChain, LlamaIndex, and the
    raw Ollama client.
  - New **§7.4 Ollama (raw client)**: coverage, request-side provider/model,
    token counts, streaming, errors, `generate`/`embed` gap, optional-client
    skip, instrument-before-first-call caveat, local-model pricing.
  - §9.2 catalog: `Ollama chat` / `Ollama error` / `Ollama redaction` /
    `Ollama stream` scenario rows.
  - §10 Deferred: the OpenAI/Anthropic line notes raw Ollama is covered.
  - §12 Decision index: `.scratch/ollama/` ticket table.
- `plans/backend.md` §8.1: local runtimes ship a seeded zero-rate provider
  default (`ollama`) → $0.00, not unpriced.
- `plans/implementation-plan.md` §5 SDK row (Ollama in the component summary)
  and §8 deferred line.
- `sdk/README.md`: intro, mock-suite counts (139 tests / 22 scenarios), failure
  catalog, and a "What the SDK emits" bullet for the raw client.

## Comments

Implemented alongside tickets 02, 03, and 05. `CONTEXT.md` and
`docs/06-project-audit.md` intentionally unchanged (no new domain term; the
audit is a dated snapshot).
