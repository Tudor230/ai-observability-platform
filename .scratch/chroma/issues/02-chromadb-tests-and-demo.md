# 02 — ChromaDB tests & demo

Type: task
Status: resolved
Blocked by: 01

## Goal

Cover the ChromaDB interceptor offline (unit tests + mock scenarios), prove it
end-to-end in the demo/UI, and update the plans and README.

## Decision

- **Fixtures**: `mock_workflows/chroma/fakes.py` runs the real client against
  `chromadb.EphemeralClient` with a deterministic keyword-count embedding
  function (`__call__` / `embed_documents` / `embed_query` plus the non-legacy
  config surface, so collection configuration emits no deprecation warnings).
  `EphemeralClient` is a process-wide singleton → `get_or_create_collection` +
  `upsert` keeps scenario/test creation idempotent.
- **Unit tests** (`tests/unit/test_chroma.py`): instrumentation guard, absent
  package skip, span shape (kind/input/documents/metadata/score/count), multiple
  query texts (JSON input + flattened results), error propagation to the root,
  capture-off redaction, uninstrument. The `test_instrumentation.py` guard tests
  were extended to ChromaDB (double-instrument detect, uninstrument, quiet skip).
- **Mock scenarios**: `chroma_query`, `chroma_query_error`, `chroma_redacted`
  (framework label `chromadb`) → suite is now 25 scenarios.
- **Demo**: `examples/ollama_chat.py`'s `fetch_policies` step now performs a real
  raw `chromadb` query against the deterministic in-memory fixture (static
  stand-in when `chromadb` is absent) inside the manual `span("fetch_policies")`,
  so the demo reproduces the OnboardingFulfillment shape.
- **Docs**: `plans/sdk.md` §2/§3/§7.5/§9.2/§10/§12,
  `plans/implementation-plan.md` §5/§8, `sdk/README.md`,
  `sdk/examples/README.md`.

## Comments

Verification (2026-09-30):

- `uv run pytest` → 151 passed, 1 skipped (was 141 + 3 new scenario params).
- `uv run aiobs-mock` → 25/25 scenarios.
- Live demo (offline `--mock`, capture on), platform backend: execution
  `24d294d866fe49acafade1c48afd5106` (`onb-e074d437`) contains
  `ollama-onboarding (CHAIN) → fetch_policies (CHAIN) → chroma.query (RETRIEVER,
  db.system=chroma, 3 docs with id/content/score) → Chat (LLM) →
  validate_plan (CHAIN)`; backend KPIs `retrieval_calls=1`, tokens 312/96,
  cost $0.00 (`cost_records` uses the seeded zero-rate ollama row).
  Dashboard: http://localhost:8080/engineering/24d294d866fe49acafade1c48afd5106
- Phoenix (`--project-id ollama-demo`): trace
  `55eb1e1bf571c313cb60e48fbde52ca3` renders the same tree with the RETRIEVER
  span under `fetch_policies`.

Follow-up (same day, "I don't see the documents"): the span now also sets
`output.value` (documents as a JSON array, `output.mime_type=application/json`)
like upstream retriever spans, and the dashboard `traceSpans.ts` additionally
synthesizes input/output from flattened `retrieval.documents.*` /
`llm.*_messages.*` when the exact keys are absent — so executions ingested
before the change render too. Re-verified: unit tests + `chroma_*` scenarios
updated; frontend suite 414 passed + typecheck/eslint clean; rebuilt dashboard
container; fresh run `464f74eaad2e4c68ab3ffdc187dce69c` (`onb-11f7b2d4`) shows
`output.value` on `chroma.query` in the DB.
