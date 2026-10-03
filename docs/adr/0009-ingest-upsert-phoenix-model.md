# ADR-0009: Phoenix-style upsert ingest — spans are first-class, executions are projections

Status: Accepted

## Context

Ingest was "idempotent per trace id" in the destructive sense: whenever a batch
arrived for a trace that already had a named execution, `process_trace()`
deleted **every** stored span and cost row for the trace and rebuilt the
execution from that batch alone
(`backend/src/aiobs_backend/ingest/pipeline.py`).

Testing the SDK against a real LangGraph human-in-the-loop app
(OnboardingFulfillment, FastAPI + LangGraph interrupt/approve) exposed two
overwrites:

1. **HITL resume wiped the interrupt run.** The interrupt and the resume are
   separate OTLP batches sharing one deterministic trace id (two sibling
   workflow roots). The resume batch hit the delete path and replaced the
   34-span interrupt execution (2 LLM calls, 3 retrievals, 1.6k tokens) with the
   7-span resume subtree — a $0 / 0-token execution in the dashboard.
2. **A partial batch fabricated a root.** The SDK's batch processor can flush
   mid-run; a batch containing `fetch_context` (OpenInference stamps
   `session.id` on LangGraph node spans from the thread id) but not its parent
   was read as a trace whose root is the node. The real-root batch then deleted
   that phantom execution's spans (`fetch_context` + 3 `chroma.query`).

Both trace back to one assumption: **a batch is the complete truth for its
trace**. Streaming SDKs and HITL flows make that false.

Phoenix models this differently: spans are stored first-class (keyed per trace
and span id), upserted on re-send; traces and sessions are projections computed
from the stored spans, and a root is simply a span whose parent is absent from
the store. Ingest never deletes observations because another arrived.

## Decision

- **Upsert spans, never delete on ingest.** Spans are keyed by
  `(execution, span_id)`: a re-sent span replaces its stored row and cost
  record, new spans append, everything else is kept. The execution row is
  created once and extended; aggregates, failure kind and timing are always
  recomputed from *all* stored spans (`_upsert_spans`, `_recompute_execution`).
- **Root election is store-aware and Phoenix-shaped.** A span is parentless
  when its parent is absent from the spans stored for the trace *plus* the
  current batch — not merely from the batch. Explicit SDK workflow roots
  (`sdk.workflow_id` / `sdk.project_id`) win; a plain parentless span
  (`workflow()` without `workflow_id`) is the fallback. `session.id` alone is
  never identity (LangGraph nodes carry it), so a children-first batch cannot
  invent a workflow root (`_resolve_identity_root`, `_is_workflow_root`).
- **Identity upgrades in place.** When the true root arrives after a
  children-first batch, only the execution's workflow identity fields are
  applied; the provisional spans stay. The first resolved root wins — a later
  HITL resume root never flaps an identified execution.
- **Continued traces coalesce.** An interrupt run and its resume (same trace
  id, two roots) live in one execution with both subtrees and union aggregates.
  Re-ingesting identical spans stays idempotent; distinct runs that share a
  pinned `workflow_id` extend the execution instead of replacing it.
- **Cross-project trace-id collisions keep the historical replace.** The
  `executions.trace_id` uniqueness is global; if a trace id already belongs to
  another project, the stored rows are replaced rather than mixing projects.
- OTLP project validation (ADR-0008) is unchanged and still runs before any
  write: every explicit workflow root in a batch is checked, conflicts are
  per-trace skips with 409 when nothing is acceptable.

## Consequences

- HITL traces show both runs in one execution (two roots, like Phoenix) with
  correct cost/token/latency aggregates; partial batches never lose earlier
  spans.
- `summary["spans"]` is now the execution's stored span count (what readers
  and the KPI gate compare) rather than the batch size.
- Repricing on re-ingest still works: cost rows for the upserted span ids are
  deleted and recomputed with the currently effective price.
- Runs sharing a pinned trace id append (the UI aggregates all of them); the
  earlier "re-run replaces" behavior is gone by design.
- `backend/tests/test_ingest.py` covers both regressions
  (`test_continued_trace_resume_extends_instead_of_replacing`,
  `test_partial_langgraph_node_is_not_the_identity_root`).

## References

- `backend/src/aiobs_backend/ingest/pipeline.py` — `process_trace`,
  `_resolve_identity_root`, `_upsert_spans`, `_recompute_execution`
- `CONTEXT.md` — glossary (trace, workflow root, execution)
- `docs/adr/0001-backend-ingest-otlp-direct.md`, `docs/adr/0008-ingest-identity-key-authoritative.md`
- `sdk/examples/README.md` — trace-continuation note
