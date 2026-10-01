# ChromaDB Raw-Client Support Map

## Destination

First-class raw **ChromaDB client** support in the SDK (`sdk/`): apps that call
`chromadb` directly (no LangChain/LlamaIndex vector store) get OpenInference
**RETRIEVER** spans — query text, retrieved documents, collection/operation
metadata, errors — nested under the manual workflow root. The map is complete
when the interceptor, wiring, tests, scenarios, demo, and plan updates are in
place, with every decision below resolved.

## Notes

- Domain: AI observability / agentic monitoring. Motivating app:
  `andrei5amabil/OnboardingFulfillment` — raw `chromadb.PersistentClient` +
  `collection.query(query_texts=[...])` inside a custom hybrid retriever
  (`src/rag/retriever.py`), pinned to `chromadb 1.5.9`, Python 3.14.
- Upstream facts (verified 2026-09-30 against chromadb 1.5.9):
  - OpenInference ships **no** ChromaDB instrumentor, and
    `openinference-instrumentation-openllmetry`'s span processor does **not**
    convert Chroma spans (they carry no `traceloop.span.kind` and no gen_ai
    message attributes).
  - Traceloop `opentelemetry-instrumentation-chromadb` (0.62.4) works on
    1.5.9 — it emits `chroma.query`/`chroma.add` spans with `db.system=chroma`,
    counts, and `db.query.result` events (id/distance/metadata/document) — but
    no OpenInference kind and **no query text** (counts only).
  - `Collection.query` is defined on `chromadb.api.models.Collection.Collection`
    (the same class `chromadb.Collection` points to); the SDK wraps it with
    `wrapt.FunctionWrapper`, the same mechanism as the LangGraph boundary patch.
- Approach settled with the user (option A): SDK-owned interceptor. Traceloop +
  conversion shim (B) and app-side manual `span()` (C) were rejected — B loses
  the query text and adds a foreign semconv dependency, C does not trace
  chromadb calls generally.

## Decisions so far

- [ChromaDB instrumentation](issues/01-chromadb-instrumentation.md): SDK-owned
  `Collection.query` interceptor → OpenInference RETRIEVER span
  (`input.value`, `retrieval.documents.*`, `db.*`), errors recorded + re-raised;
  unified optional-framework wiring (skip when absent, safe instrument, foreign
  wrapper guard).
- [ChromaDB tests & demo](issues/02-chromadb-tests-and-demo.md): offline
  `EphemeralClient` + deterministic embedding-function fixtures; `chroma_query`,
  `chroma_query_error`, `chroma_redacted` mock scenarios; the Ollama demo's
  retrieval step now runs a real chromadb query; plan/README updates.

## Not yet specified

- Async `AsyncCollection.query` and ingestion calls (`add`/`upsert`/`get`) —
  out of v1 scope.
- Other vector stores (Qdrant, pgvector, Weaviate) — the same interceptor shape
  if needed.
- OnboardingFulfillment-side integration (`init()` + `workflow()` wrapping) —
  lives in that repo; the interceptor needs no app changes.

## Out of scope

- Replacing the app's hybrid retriever (RRF + cross-encoder) — only the raw
  chroma call is instrumented; the rest stays app-owned (manual `span()`).
- Changes to the app being monitored.
