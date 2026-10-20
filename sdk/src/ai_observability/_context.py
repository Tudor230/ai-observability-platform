"""Shared span-parent helpers for the SDK-owned instrumentors.

OpenInference's LangChain tracer links its spans through its own run tree and
deliberately does not attach them to the OTel context. Raw instrumentors (Chroma,
Databricks AI Search) would therefore parent to the nearest manually attached
span — the workflow root or a graph wrapper — rather than the LangGraph node
executing the call. ``get_current_span`` bridges that gap for both.
"""

from __future__ import annotations

import logging

from opentelemetry import trace as trace_api
from opentelemetry.context import Context

logger = logging.getLogger(__name__)


def langchain_parent_context() -> Context | None:
    """Explicit parent for the active LangChain/LangGraph run, when there is one.

    Returns ``None`` outside a LangChain run (or when the active run belongs to
    a different trace), leaving the ambient context as the parent.
    """
    try:
        from openinference.instrumentation.langchain import get_current_span
    except Exception:  # noqa: BLE001 - optional dependency/import guard
        # LangChain is optional: without it there is no run context to bridge.
        return None
    try:
        span = get_current_span()
    except Exception:
        logger.debug("LangChain current-span lookup failed", exc_info=True)
        return None
    if span is None:
        return None
    span_context = span.get_span_context()
    if not span_context.is_valid:
        return None
    ambient = trace_api.get_current_span().get_span_context()
    if ambient.is_valid and ambient.trace_id != span_context.trace_id:
        # A stale run config from another trace must never relink the span.
        return None
    return trace_api.set_span_in_context(span)
