"""Deterministic trace-id derivation (Langfuse-style trace continuation).

Human-in-the-loop splits one LangGraph thread across several executions: the
interrupt and the resume are separate requests (often separate processes or
hosts), each with its own ``workflow()`` root span. To make them render as ONE
trace, the trace id is derived deterministically from a stable seed — the
``workflow_id``, which the app sets to the LangGraph ``thread_id`` — instead of
being random. Every execution of the same thread recomputes the same trace id
and joins the same trace. No shared store is needed, so it works across
processes and hosts with zero coordination.

A continued run's root span is created under a *synthetic* remote parent: the
parent span id is arbitrary and does not exist within the trace — it only
carries the trace id for inheritance. This mirrors Langfuse's
``create_trace_id(seed=...)`` + ``trace_context`` continuation model.
"""

from __future__ import annotations

import hashlib

from opentelemetry.trace import (
    Context,
    NonRecordingSpan,
    SpanContext,
    TraceFlags,
)
from opentelemetry.trace.propagation import set_span_in_context

#: Arbitrary valid 64-bit span id for the synthetic parent. The parent span does
#: not exist within the trace; it only provides the trace id for inheritance.
_SYNTHETIC_SPAN_ID = 1


def trace_id_from_seed(seed: str) -> int:
    """Deterministic 128-bit OTel trace id derived from ``seed``."""
    digest = hashlib.sha256(seed.encode("utf-8")).digest()[:16]
    trace_id = int.from_bytes(digest, "big")
    # Guard against the invalid all-zero id (practically unreachable).
    return trace_id or 1


def parent_context_for_trace(seed: str) -> Context:
    """Context whose synthetic parent pins the trace id to ``seed``.

    Start a root span with this context to make it a root of the deterministic
    trace for ``seed`` (fresh span id, inherited trace id). When the current
    context already has an active span (nesting), callers must NOT use this —
    normal parenting wins there.
    """
    span_context = SpanContext(
        trace_id=trace_id_from_seed(seed),
        span_id=_SYNTHETIC_SPAN_ID,
        is_remote=True,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )
    return set_span_in_context(NonRecordingSpan(span_context))