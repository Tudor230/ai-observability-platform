# 03 — Groq pricing & docs

Type: task
Status: resolved
Blocked by: 02

## Decision

Groq is a **hosted, billed provider** — no zero-rate row (unlike local Ollama,
`.scratch/ollama/issues/05`). Seed its published list rates so the models the
hosted demos default to are priced out of the box:

- `groq` / `openai/gpt-oss-120b` exact: $0.15 in, $0.60 out, $0.075 cache read
- `groq` / `openai/gpt-oss-20b` exact: $0.075 in, $0.30 out

The existing `groq`/`llama-` prefix row stays. A free-tier deployment that
wants $0.00 instead can delete or replace the rows — documented in
`plans/backend.md` §8.1 (a free tier is a billing state, not a model property).

## Changes

- `backend/src/aiobs_backend/seed.py` + `backend/tests/conftest.py` seeding.
- `backend/tests/test_pricing.py::test_groq_gpt_oss_uses_seeded_list_rate`.
- `plans/sdk.md` (§2, §3, §7.6, §9.2, §10, §12), `plans/backend.md` §8.1,
  `plans/implementation-plan.md` (§5, §8), `sdk/README.md`.

## Comments

Implemented. Groq instrumentation is complete: wiring, offline unit tests, mock
scenarios, seeded pricing, and docs.
