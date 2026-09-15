"""Authoritative failure classification (plans/backend.md §7).

The backend owns the taxonomy (``aiobs_contracts.ERROR_KINDS``). The SDK's
``sdk.error.kind`` is a hint: it is trusted when present, but refined when the
raw material clearly indicates a more specific kind (rate limit / timeout /
invalid output / validation).
"""
from __future__ import annotations

import aiobs_contracts as c

from . import attrs
from .ingest.otlp import RawSpan

VALID_KINDS = c.ERROR_KINDS
_SDK_HINTS = c.SDK_HINTS


def _normalize_hint(kind: str | None) -> str | None:
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

    events = attrs.real_exception_events(span)
    if events:
        ev = events[0]
        error_type = error_type or ev.get("type")
        error_message = error_message or ev.get("message")

    error_message = error_message or span.status_message
    oi_kind = attrs.span_kind(span)
    hint = _normalize_hint(attrs.as_str(span.attributes, attrs.SDK_ERROR_KIND))

    kind = _authoritative_kind(hint, oi_kind, error_type, error_message)

    if kind is None and span.status_code == "error" and oi_kind in {
        attrs.KIND_CHAIN,
        attrs.KIND_AGENT,
    }:
        # An upper-layer failure with no lower-layer classification.
        kind = c.KIND_BUSINESS_LOGIC

    return kind, error_type, error_message


def _authoritative_kind(
    hint: str | None, oi_kind: str, error_type: str | None, error_message: str | None
) -> str | None:
    """Combine the SDK hint with the backend's own reading of the raw material.

    Trust the hint, but override it when the raw text clearly indicates a more
    specific kind (the backend is authoritative).
    """
    raw_hint = c.match_hint(f"{error_type or ''} {error_message or ''}")

    if raw_hint is not None:
        if hint is None or raw_hint in _specific_kinds() or _more_specific(raw_hint, hint):
            return raw_hint
        return hint

    if hint is not None:
        return hint

    # No hint and no textual signal: attribute to the failing layer.
    if oi_kind in c.LAYER_ERROR_KIND:
        return c.LAYER_ERROR_KIND[oi_kind]
    return None


def _specific_kinds() -> set[str]:
    return {c.KIND_RATE_LIMIT, c.KIND_TIMEOUT, c.KIND_INVALID_OUTPUT, c.KIND_VALIDATION_ERROR}


def _more_specific(raw_hint: str, hint: str) -> bool:
    """Rate limit / timeout / invalid output beat generic layer hints."""
    specific = {c.KIND_RATE_LIMIT, c.KIND_TIMEOUT, c.KIND_INVALID_OUTPUT}
    return raw_hint in specific and hint in {c.KIND_TOOL_ERROR, c.KIND_PROVIDER_ERROR, c.KIND_RETRIEVAL_ERROR}


def is_failed(span: RawSpan) -> bool:
    """True when the span carries a real failure.

    Mirrors the SDK: control-flow exceptions (``GraphInterrupt`` & co) only
    pause execution and are not failures. An ERROR status with no exception
    event still counts as a failure (an instrumentor can set ERROR without
    recording an event).
    """
    events = attrs.exception_events(span)
    real_events = [e for e in events if not c.is_control_flow_exception(e.get("type"))]
    if span.status_code == "error":
        if real_events:
            return True
        return not events
    if attrs.as_str(span.attributes, attrs.SDK_ERROR_KIND):
        return True
    return bool(real_events)