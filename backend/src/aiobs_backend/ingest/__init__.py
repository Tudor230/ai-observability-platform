"""Telemetry ingestion: OTLP decode → normalize → persist as executions/spans."""
from .otlp import RawSpan, decode_trace_export

__all__ = ["RawSpan", "decode_trace_export"]