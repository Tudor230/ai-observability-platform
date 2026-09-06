"""Failure capture: sdk.error.* attribute derivation and classification hints.

The SDK records raw material (exception type/message, span status, span kind)
plus best-effort ``sdk.error.kind`` hints. The backend holds the authoritative
failure taxonomy and may trust or override these hints.
"""

from __future__ import annotations

from typing import Optional

from opentelemetry.sdk.trace import ReadableSpan

from ._attributes import (
    EXCEPTION_EVENT_NAME,
    EXCEPTION_MESSAGE,
    EXCEPTION_TYPE,
    OPENINFERENCE_SPAN_KIND,
    SDK_ERROR_KIND,
    SDK_ERROR_MESSAGE,
    SDK_ERROR_TYPE,
)

# Best-effort classification hints (backend may override). Order matters:
# specific signals first, generic fallbacks last.
_KIND_RATE_LIMIT = "rate_limit"
_KIND_TIMEOUT = "timeout"
_KIND_INVALID_OUTPUT = "invalid_output"
_KIND_TOOL_ERROR = "tool_error"
_KIND_PROVIDER_ERROR = "provider_error"


def has_exception_event(span: ReadableSpan) -> bool:
    return any(event.name == EXCEPTION_EVENT_NAME for event in span.events)


def is_failed(span: ReadableSpan) -> bool:
    from opentelemetry.trace.status import StatusCode

    if span.status and span.status.status_code == StatusCode.ERROR:
        return True
    return has_exception_event(span)


def exception_type_message(span: ReadableSpan) -> tuple[Optional[str], Optional[str]]:
    for event in span.events:
        if event.name != EXCEPTION_EVENT_NAME:
            continue
        attrs = dict(event.attributes or {})
        exc_type = attrs.get(EXCEPTION_TYPE)
        exc_message = attrs.get(EXCEPTION_MESSAGE)
        return (
            exc_type if isinstance(exc_type, str) else None,
            exc_message if isinstance(exc_message, str) else None,
        )
    return None, None


def classify_kind(*, exception_type: Optional[str], exception_message: Optional[str], span_kind: Optional[str]) -> Optional[str]:
    t = (exception_type or "").lower()
    m = (exception_message or "").lower()
    if (
        "ratelimit" in t
        or "rate limit" in t
        or "throttl" in t
        or "429" in m
    ):
        return _KIND_RATE_LIMIT
    if "timeout" in t or "timed out" in t or "deadline" in t:
        return _KIND_TIMEOUT
    if (
        "jsondecodeerror" in t
        or "outputparser" in t
        or ("json" in t and ("decode" in t or "parse" in t))
        or ("json" in m and "expecting value" in m)
    ):
        return _KIND_INVALID_OUTPUT
    if span_kind == "TOOL":
        return _KIND_TOOL_ERROR
    if span_kind == "LLM":
        return _KIND_PROVIDER_ERROR
    return None


def enrich_error_attributes(span: ReadableSpan, attributes: dict) -> dict:
    """Stamp sdk.error.type/message/kind on a copy of ``attributes``."""
    status = span.status
    exc_type, exc_message = exception_type_message(span)
    span_kind = attributes.get(OPENINFERENCE_SPAN_KIND)

    if exc_type is not None:
        attributes[SDK_ERROR_TYPE] = exc_type
    message = exc_message
    if message is None and status is not None and status.description:
        message = status.description
    if message is not None:
        attributes[SDK_ERROR_MESSAGE] = message

    if SDK_ERROR_KIND not in attributes:
        kind = classify_kind(
            exception_type=exc_type,
            exception_message=message,
            span_kind=span_kind,
        )
        if kind is not None:
            attributes[SDK_ERROR_KIND] = kind
    return attributes