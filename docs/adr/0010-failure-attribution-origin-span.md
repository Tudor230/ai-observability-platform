# ADR-0010: Failure attribution — the origin span carries the kind, ancestors keep the status

Status: Accepted

## Context

Instrumentors mark **every ancestor** of a raising span as ERROR: an exception
from an LLM call passes through `ChatOllama → RunnableParallel → RunnableSequence
→ llm_planning → LangGraph → workflow root`, and OpenInference records it on each
of those spans. Phoenix renders the same; the statuses are faithful.

The platform layered a taxonomy on top (`classify.py`): failing spans without a
lower-layer signal fall back to `business_logic` for CHAIN/AGENT. As a result,
every wrapper in the chain was stored with `error_kind=business_logic` plus the
propagated message, and the execution's root cause was picked by an
earliest-failed heuristic that could select the (unclassified) root — masking
the real `provider_error` from the LLM span. The SDK's own root propagation had
the mirror problem: it took the earliest failed span, which is usually the
unclassified root, so `sdk.error.kind` never reached the root when the root
itself failed.

The plan already intended otherwise: "Root propagation: the execution root's
failure is the earliest/deepest root cause" (`plans/backend.md` §7.2, F28).

## Decision

- **Statuses are recorded, not rewritten.** Every span the instrumentor marked
  ERROR stays ERROR — that is the raw material and matches Phoenix.
- **Kinds belong to the origin.** The backend clears the generic
  `business_logic` classification from a wrapper CHAIN/AGENT when its subtree
  contains a classified failure (it only re-raised a descendant's failure).
  A wrapper with no classified descendant keeps `business_logic` — that is a
  genuine upper-layer failure (`_attribute_failure`).
- **The execution reports the earliest classified failure** (falling back to
  the earliest failed span when nothing is classified); its `error_kind` and
  `error_message` are the origin's.
- **The SDK root inherits the earliest *classified* descendant's kind**
  (`_propagate_root_failure`), so `sdk.error.kind` on the workflow root is
  accurate for Phoenix even when the root itself is a failed wrapper.

## Consequences

- The Engineering list shows `provider_error`/`rate_limit`/… for failed
  executions instead of a blanket `business_logic`.
- The failure tree still contains every errored span (status + propagated
  message), but only the origin shows a kind; the UI's generic "error" badge is
  reserved for wrappers that only propagated a child's failure.
- `error_count` remains the number of errored spans; `failed_executions` and
  the per-kind analytics keep using the execution's origin kind.
- Reconstruction is idempotent with ADR-0009: every re-ingest recomputes
  attribution from the full stored span set, so a descendant arriving in a
  later batch upgrades a wrapper from `business_logic` to unclassified.

## References

- `backend/src/aiobs_backend/ingest/pipeline.py` — `_attribute_failure`
- `backend/src/aiobs_backend/classify.py` — upper-layer fallback
- `sdk/src/ai_observability/_enrichment.py` — `_propagate_root_failure`
- `docs/adr/0009-ingest-upsert-phoenix-model.md`
- `plans/backend.md` §7.2 (F28)
