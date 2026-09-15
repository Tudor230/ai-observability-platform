"""Failure capture: sdk.error.* attribute derivation and classification hints.

The SDK records raw material (exception type/message, span status, span kind)
plus best-effort ``sdk.error.kind`` hints. The backend holds the authoritative
failure taxonomy and may trust or override these hints. Names and hint patterns
are shared with the backend via ``aiobs_contracts``.
"""

from __future__ import annotations

from typing import Optional

from aiobs_contracts import (
    KIND_LLM,
    KIND_PROVIDER_ERROR,
    KIND_TIMEOUT,
    KIND_TOOL,
    KIND_TOOL_ERROR,
    is_control_flow_exception,
    match_hint,
)
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

def has_exception_event(span: ReadableSpan) -> bool:
    return any(event.name == EXCEPTION_EVENT_NAME for event in span.events)


def _is_control_flow_event(event) -> bool:
    exc_type = (event.attributes or {}).get(EXCEPTION_TYPE)
    if not isinstance(exc_type, str):
        return False
    return is_control_flow_exception(exc_type)


def _is_real_exception_event(event) -> bool:
    return event.name == EXCEPTION_EVENT_NAME and not _is_control_flow_event(event)


def is_failed(span: ReadableSpan) -> bool:
    """True when the span carries a real failure.

    Control-flow exceptions (``GraphInterrupt`` & co) are excluded: they only
    pause execution. An ERROR status with no exception event still counts as a
    failure (the instrumentor can set ERROR status without recording an event).
    """
    from opentelemetry.trace.status import StatusCode

    is_error_status = span.status is not None and span.status.status_code == StatusCode.ERROR
    has_real_event = any(_is_real_exception_event(event) for event in span.events)
    if is_error_status:
        if has_real_event:
            return True
        if not has_exception_event(span):
            return True
        return False
    return has_real_event


def exception_type_message(span: ReadableSpan) -> tuple[Optional[str], Optional[str]]:
    for event in span.events:
        if not _is_real_exception_event(event):
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
    combined = " ".join(p for p in (exception_type or "", exception_message or "") if p)
    hint = match_hint(combined)
    if hint is not None:
        return hint
    if span_kind == KIND_TOOL:
        return KIND_TOOL_ERROR
    if span_kind == KIND_LLM:
        return KIND_PROVIDER_ERROR
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