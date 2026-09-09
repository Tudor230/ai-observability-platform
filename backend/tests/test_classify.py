"""Failure classification unit tests (backend authoritative taxonomy)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiobs_backend.classify import classify_span
from aiobs_backend.ingest.otlp import RawSpan


def _now():
    return datetime.now(timezone.utc)


def _span(oi_kind: str, message: str | None = None, attrs: dict | None = None) -> RawSpan:
    now = _now()
    return RawSpan(
        trace_id="00" * 16,
        span_id="01" * 8,
        parent_span_id=None,
        name="s",
        start_time=now,
        end_time=now + timedelta(seconds=1),
        status_code="error",
        status_message=message,
        attributes={"openinference.span.kind": oi_kind, **(attrs or {})},
        events=[],
    )


def test_hint_trusted_when_specific():
    span = _span("LLM", "upstream exploded", {"sdk.error.kind": "provider_error"})
    kind, etype, emsg = classify_span(span)
    assert kind == "provider_error"


def test_hint_overridden_by_more_specific_signal():
    # SDK says provider_error, but raw text clearly indicates a rate limit.
    span = _span(
        "LLM",
        "429 rate limit exceeded",
        {"sdk.error.kind": "provider_error", "sdk.error.message": "429 rate limit exceeded"},
    )
    kind, _, _ = classify_span(span)
    assert kind == "rate_limit"


def test_validation_error_on_chain():
    span = _span("CHAIN", "pydantic ValidationError: 1 validation error")
    kind, _, _ = classify_span(span)
    assert kind == "validation_error"


def test_layer_fallback_when_no_signal():
    span = _span("TOOL", "boom")
    kind, _, _ = classify_span(span)
    assert kind == "tool_error"


def test_retriever_fallback():
    span = _span("RETRIEVER", "boom")
    kind, _, _ = classify_span(span)
    assert kind == "retrieval_error"


def test_chain_business_logic_when_unclassified():
    span = _span("CHAIN", "unknown failure")
    kind, _, _ = classify_span(span)
    assert kind == "business_logic"