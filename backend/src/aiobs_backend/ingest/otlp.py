"""Decode OTLP `ExportTraceServiceRequest` protobuf bodies into normalized raw spans."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from google.protobuf.message import DecodeError
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from opentelemetry.proto.common.v1.common_pb2 import AnyValue
from opentelemetry.proto.trace.v1.trace_pb2 import Span as OtlpSpan

# OTel StatusCode enum
_STATUS_OK = 1
_STATUS_ERROR = 2


class InvalidOtlpPayload(ValueError):
    """Raised when an ingest body is not a valid OTLP trace export."""


@dataclass
class RawSpan:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    start_time: datetime | None
    end_time: datetime | None
    status_code: str  # ok | error | unset
    status_message: str | None
    attributes: dict[str, object] = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)


def _any_value(av: AnyValue) -> object:
    which = av.WhichOneof("value")
    if which == "string_value":
        return av.string_value
    if which == "bool_value":
        return av.bool_value
    if which == "int_value":
        return av.int_value
    if which == "double_value":
        return av.double_value
    if which == "array_value":
        return [_any_value(v) for v in av.array_value.values]
    if which == "kvlist_value":
        return {kv.key: _any_value(kv.value) for kv in av.kvlist_value.values}
    if which == "bytes_value":
        return av.bytes_value
    return None


def _attrs_to_dict(attr_list) -> dict[str, object]:
    return {kv.key: _any_value(kv.value) for kv in attr_list}


def _nano_to_dt(nano: int) -> datetime | None:
    if not nano:
        return None
    return datetime.fromtimestamp(nano / 1_000_000_000, tz=timezone.utc)


def _span_from_otlp(span: OtlpSpan) -> RawSpan:
    attrs = _attrs_to_dict(span.attributes)
    events = []
    for ev in span.events:
        events.append({"name": ev.name, "attributes": _attrs_to_dict(ev.attributes)})
    if span.status.code == _STATUS_ERROR:
        status = "error"
    elif span.status.code == _STATUS_OK:
        status = "ok"
    else:
        status = "unset"
    return RawSpan(
        trace_id=span.trace_id.hex(),
        span_id=span.span_id.hex(),
        parent_span_id=span.parent_span_id.hex() if span.parent_span_id else None,
        name=span.name,
        start_time=_nano_to_dt(span.start_time_unix_nano),
        end_time=_nano_to_dt(span.end_time_unix_nano),
        status_code=status,
        status_message=span.status.message or None,
        attributes=attrs,
        events=events,
    )


def decode_trace_export(body: bytes) -> list[RawSpan]:
    """Parse an OTLP HTTP protobuf body into raw spans (F21).

    Malformed bodies raise :class:`InvalidOtlpPayload` so the API can answer
    400 instead of a 500.
    """
    request = ExportTraceServiceRequest()
    try:
        request.ParseFromString(body)
    except DecodeError as exc:
        raise InvalidOtlpPayload(str(exc)) from exc
    raw: list[RawSpan] = []
    for resource_spans in request.resource_spans:
        for scope_spans in resource_spans.scope_spans:
            for otlp_span in scope_spans.spans:
                raw.append(_span_from_otlp(otlp_span))
    return raw