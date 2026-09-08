"""Authoritative failure classification (plans/backend.md §7).

The backend owns the taxonomy; the SDK's `sdk.error.kind` is a hint that is
trusted when present and refined/derived from raw material otherwise.
"""
from __future__ import annotations

import re

from . import attrs
from .ingest.otlp import RawSpan

VALID_KINDS = {
    "rate_limit",
    "timeout",
    "invalid_output",
    "tool_error",
    "provider_error",
    "retrieval_error",
    "validation_error",
    "business_logic",
}

_HINT_RATE_LIMIT = re.compile(r"ratelimit|rate.?limit|throttl|429")
_HINT_TIMEOUT = re.compile(r"timeout|timed.?out|deadline")
_HINT_INVALID = re.compile(
    r"jsondecodeerror|outputparser|expecting value|json\.decode|parse.?error"
    r"|invalid json|validation error"
)


def _classify_hint(kind: str) -> str | None:
    """Normalize an SDK hint into the authoritative taxonomy."""
    if kind in VALID_KINDS:
        return kind
    return None


def classify_span(span: RawSpan) -> tuple[str | None, str | None, str | None]:
    """Return (error_kind, error_type, error_message) for a failing span.

    Uses SDK attributes first, then falls back to exception events + span
    kind/status-derived heuristics.
    """
    error_type = attrs.as_str(span.attributes, attrs.SDK_ERROR_TYPE)
    error_message = attrs.as_str(span.attributes, attrs.SDK_ERROR_MESSAGE)

    events = attrs.exception_events(span)
    if events:
        ev = events[0]
        error_type = error_type or ev.get("type")
        error_message = error_message or ev.get("message")

    error_message = error_message or span.status_message
    oi_kind = attrs.span_kind(span)
    hint = _classify_hint(attrs.as_str(span.attributes, attrs.SDK_ERROR_KIND))

    if hint:
        kind = hint
    else:
        kind = _derive_kind(oi_kind, error_type, error_message)

    if kind is None and span.status_code == "error" and oi_kind in {
        attrs.KIND_CHAIN,
        attrs.KIND_AGENT,
    }:
        # An upper-layer failure with no lower-layer classification.
        kind = "business_logic"

    return kind, error_type, error_message


def _derive_kind(oi_kind: str, error_type: str | None, error_message: str | None) -> str | None:
    combined = " ".join(
        part.lower() for part in (error_type, error_message) if part
    )
    if not combined and oi_kind in {attrs.KIND_LLM, attrs.KIND_TOOL, attrs.KIND_RETRIEVER}:
        # Raw ERROR with no text: attribute to the layer.
        return {
            attrs.KIND_LLM: "provider_error",
            attrs.KIND_TOOL: "tool_error",
            attrs.KIND_RETRIEVER: "retrieval_error",
        }[oi_kind]
    if _HINT_RATE_LIMIT.search(combined):
        return "rate_limit"
    if _HINT_TIMEOUT.search(combined):
        return "timeout"
    if _HINT_INVALID.search(combined):
        return "invalid_output"
    if oi_kind == attrs.KIND_TOOL:
        return "tool_error"
    if oi_kind == attrs.KIND_RETRIEVER:
        return "retrieval_error"
    if oi_kind == attrs.KIND_LLM:
        return "provider_error"
    return None


def is_failed(span: RawSpan) -> bool:
    if span.status_code == "error":
        return True
    if attrs.as_str(span.attributes, attrs.SDK_ERROR_KIND):
        return True
    return bool(attrs.exception_events(span))