# Trace-id continuation for HITL (one trace per thread)

Type: grilling
Status: resolved
Blocked by: 05

## Question

How should the SDK link the interrupt run and its resume run so they render as ONE trace (not two traces grouped by session), and how does a production-grade implementation avoid a shared store?

## Answer

Decided by grilling with the user: **deterministic trace-id derivation from a stable seed — Langfuse's model — with no store at all.**

### Why not a store

The first plan was a `TraceLinkStore` (thread_id → trace context), JSON-file-backed to survive processes. The user pushed back: JSON-on-disk is not production-grade. Research into how Langfuse does it (docs: "Trace IDs & Distributed Tracing") showed they **persist nothing**:

- `create_trace_id(seed="<external-id>")` derives a deterministic 128-bit trace id from a seed (e.g. a support ticket id / thread id).
- On the resumed run the app recomputes the same id from the same seed and starts the new observation with `trace_context={"trace_id": <derived>, "parent_span_id": <arbitrary valid hex>}`.
- Langfuse's docs are explicit that the parent span id is arbitrary: *"the span does not actually exist within the trace but is only used for trace ID inheritance"* (a synthetic remote parent — the exact OTel remote-parent trick).

No shared store ⇒ no races, no cross-process coordination, works across hosts. The "persistence" is the stable external id the app already holds on both calls (the LangGraph `thread_id`).

### What we built

- **`_ids.py`** — `trace_id_from_seed(seed)` (sha256 → 128-bit OTel trace id, non-zero guarded) and `parent_context_for_trace(seed)` (synthetic remote `SpanContext` + `NonRecordingSpan` → `set_span_in_context`).
- **`_workflow.py` `Workflow.__enter__`** — when `workflow_id` is set and the current context has NO active parent span (a true root), start the root span with the derived parent context, so every execution of the same `workflow_id` inherits the same trace id. Nesting is never hijacked: if an active span is current, normal parenting wins.
- **`_state.py` `HITLRegistry`** — key changed from `trace_id` to `(trace_id, root_span_id)` (compound), because a continued trace has two root spans sharing one trace id and each export batch takes only its own pending attributes (interrupt batch pops its own; resume batch pops its own).
- **`_enrichment.py` `_enrich`** — handles MULTIPLE roots per trace (the continuation case): each root gets `_apply_hitl` + `_propagate_root_failure`, with failure propagation scoped to the root's own subtree (a failed resume child no longer flips the already-completed interrupt root). Single-root traces keep the original "every other span is a descendant" contract.
- **`_langgraph.py`** — resume now also records `sdk.hitl.resumed="true"` (plus the existing `interrupted="false"`, `resume_value`, `checkpoint_id`); interrupt records `interrupted="true"`, payload, `thread_id`, derived `node`. `_record_hitl` uses the compound key.
- **Hint** — the enricher logs a warning when an interrupt trace has no `session.id`: "set `workflow(..., workflow_id=<thread_id>)` so interrupt and resume group into one trace".

### The seed is `workflow_id`

The app sets `workflow(workflow_id=thread_id)` (both the demo and any LangGraph server do this — the thread id is mandatory to run a thread). Both the interrupt request and the resume request pass the same `workflow_id`, so both recompute the same trace id. `workflow_id` stays optional; without it the SDK falls back to random trace ids (two separate traces, the old behavior).

### Rendering

Both runs' roots carry the same synthetic remote parent id, so Phoenix renders ONE trace with two entry points (Langfuse does the same). `dev/inspect_traces.py` was updated to treat a span as a root when its parent is absent from the trace (NULL or synthetic).

### Trade-offs (documented)

- Two concurrent workflows reusing the same `workflow_id` merge into one trace. For LangGraph threads this is correct-by-design (a thread is sequential); for unrelated business ids it is a footgun — could be namespaced with `workflow.name` later if ever needed.
- Both runs of a continued trace are sibling roots (each under the synthetic parent), not parent/child — we cannot point the resume root at the interrupt root's real span id without a store, and the user chose no-store determinism.
- Deterministic ids are always sampled (HITL is exactly what you want to keep).