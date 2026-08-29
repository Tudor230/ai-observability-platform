# Assemble the plan MDs

Type: task
Status: resolved
Blocked by: 01, 02, 03, 04, 05, 06, 07

## Question

Write `plans/implementation-plan.md` — assembled from `docs/01`–`docs/05` plus every decision on this map, with deferred items clearly marked — and `plans/sdk.md` from all SDK decisions. The answer records the resulting file paths and what each contains.

## Answer

Both plan documents written:

- **`plans/implementation-plan.md`** — rough platform-wide plan: vision, problem, target users, architecture (from docs 01–05), component table with status/owner, phased roadmap (SDK → backend → dashboard → alerts), cross-cutting decisions, deferred items, out of scope.
- **`plans/sdk.md`** — detailed SDK plan: purpose/scope, architecture, config & init (env vars, OTLP headers), trace model (workflow wrapper API, attributes, hierarchy), failure & usage capture, retries, auto-instrumentation scope (LangChain/LlamaIndex), export reliability, mock-workflow harness, deferred work, and a decision index linking every decision to its wayfinder ticket.