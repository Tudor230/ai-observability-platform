# 01 — ChromaDB instrumentation

Type: task
Status: resolved
Blocked by: —

## Goal

Decide how raw `chromadb` Python client calls become spans in the SDK:
reuse an existing instrumentor (Traceloop), bridge its spans to OpenInference,
or own a minimal interceptor.

## Options considered

| Option | Outcome |
|---|---|
| **A. SDK-owned interceptor** (chosen) | Wrap `Collection.query` with `wrapt`, emit an OpenInference **RETRIEVER** span directly: query text as `input.value`, hits as `retrieval.documents.*`, `db.system`/`db.operation`/`db.collection.name`; errors recorded + re-raised. No new dependency; matches how the SDK already owns what OpenInference lacks (`_langgraph.py`). |
| B. Traceloop `opentelemetry-instrumentation-chromadb` + conversion shim | Works on chromadb 1.5.9, but spans carry no OpenInference kind and **no query text** (counts only); result documents arrive as `db.query.result` events needing a converter; adds `opentelemetry-semconv-ai`; the Arize OpenLLMetry bridge does not convert Chroma. Rejected. |
| C. App-side manual `span("fetch_policies")` | Quick, but per-app, requires manual document attributes, and does not trace chromadb calls for anyone else. Rejected as the fix (still valid for the app's RRF/cross-encoder code). |

## Decision

**Option A**: a minimal SDK-owned interceptor in `_chroma.py`, wired like the
other instrumentors (availability guard → double-instrument guard → safe
instrument; `uninstrument()` restores the original method).

- **Span shape**: `chroma.query` (OpenInference **RETRIEVER**, OTel INTERNAL),
  nested under the active workflow root; `input.mime_type` is `text/plain` for a
  single query text and `application/json` for several; `document.score` is the
  Chroma distance (matching LangChain's Chroma wrapper, which records distances
  in the same slot); `chroma.query.result_count` is a redaction-safe metric.
  Follow-up: the span also sets `output.value` (documents as a JSON array) like
  upstream retriever spans, so generic viewers (dashboard Output tab, Phoenix)
  show the retrieved documents without frontend special-casing.
- **Payload policy**: recorded by the interceptor, stripped at export by the
  enrichment layer when `capture_prompts` is off (`input.value` /
  `retrieval.documents.*` are payload attributes in the shared contracts).
- **Errors**: OTel span-context-manager defaults record the exception event and
  set ERROR status; the exception re-raises unchanged. Backend maps RETRIEVER
  failures to `retrieval_error`.
- **Scope**: sync `Collection.query` only — the runtime retrieval path. No
  `add`/`upsert`/`get`, no async client (ingestion runs offline in the app's
  ETL script).
- **Optional package**: `chromadb` is a dev dependency of this repo; `init()`
  skips quietly (debug) when it is absent, and a foreign wrapper on
  `Collection.query` triggers the double-instrumentation warning.
- **No ADR**: extends the established "reuse OpenInference; own only what it
  lacks" pattern; the record lives here and in the plans.

## Comments

Implemented 2026-09-30. Key implementation notes:

- `_query_owner()` walks the MRO so the wrapper lands on whichever class defines
  `query` (1.5.9: `chromadb.api.models.Collection.Collection`).
- The guard checks `FunctionWrapper` in the class `__dict__` — `Collection.query`
  access returns a binding proxy, not the wrapper itself, which made the naive
  `isinstance` check fail during the spike against Traceloop's instrumentation.
- Call arguments are normalized with `inspect.signature(...).bind()` so
  positional calls are captured too (the app uses keywords).
- `_query_texts` accepts `str` or `Sequence[str]` (chromadb allows both).

Evidence: `uv run pytest` 151 passed + 1 skipped; `uv run aiobs-mock` 25/25;
demo execution with a RETRIEVER span exported to the platform (see ticket 02).
