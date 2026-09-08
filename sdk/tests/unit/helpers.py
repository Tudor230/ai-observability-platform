"""Helpers for building synthetic spans and exercising the enrichment layer."""

from __future__ import annotations

from typing import Optional

from opentelemetry.sdk.trace import Event, ReadableSpan
from opentelemetry.trace import SpanContext, TraceFlags
from opentelemetry.trace.status import Status, StatusCode

from ai_observability._attributes import OPENINFERENCE_SPAN_KIND


def make_span(
    span_id: int,
    trace_id: int,
    parent_id: Optional[int] = None,
    *,
    name: str = "step",
    kind: str = "CHAIN",
    status_code: StatusCode = StatusCode.OK,
    status_description: Optional[str] = None,
    attributes: Optional[dict] = None,
    events: Optional[list[Event]] = None,
    start_time: int = 1_000_000_000,
    end_time: int = 1_000_010_000,
    parent_remote: bool = False,
) -> ReadableSpan:
    context = SpanContext(
        trace_id=trace_id,
        span_id=span_id,
        is_remote=False,
        trace_flags=TraceFlags(1),
    )
    parent = (
        SpanContext(
            trace_id=trace_id,
            span_id=parent_id,
            is_remote=parent_remote,
            trace_flags=TraceFlags(1),
        )
        if parent_id is not None
        else None
    )
    attrs = dict(attributes or {})
    attrs.setdefault(OPENINFERENCE_SPAN_KIND, kind)
    return ReadableSpan(
        name=name,
        context=context,
        parent=parent,
        attributes=attrs,
        events=events or [],
        status=Status(status_code, description=status_description),
        start_time=start_time,
        end_time=end_time,
    )


def exception_event(exc_type: str, message: str) -> Event:
    return Event(
        name="exception",
        attributes={"exception.type": exc_type, "exception.message": message},
    )


def enrich(spans: list[ReadableSpan], config, *, flush: bool = True) -> list[ReadableSpan]:
    """Run spans through the enrichment exporter and return enriched copies."""
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    from ai_observability._enrichment import EnrichingExporter

    sink = InMemorySpanExporter()
    exporter = EnrichingExporter(config, sink)
    exporter.export(spans)
    if flush:
        exporter.force_flush()
    return list(sink.get_finished_spans())


def as_dict(spans: list[ReadableSpan]) -> dict[int, dict]:
    return {s.context.span_id: dict(s.attributes or {}) for s in spans}