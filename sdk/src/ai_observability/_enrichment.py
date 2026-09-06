"""Post-end enrichment pipeline (the SDK's export layer).

Instrumentor- and SDK-created spans are immutable once ended, yet the SDK
must retroactively stamp ``sdk.error.*``/``sdk.retry.*`` attributes, fill
providers and token counts, propagate failures to the workflow root, and
enforce prompt-capture redaction. All of that happens here: a decorator
``SpanExporter`` between the BatchSpanProcessor and the OTLP exporter that
deep-copies each trace's spans and stamps the copies before serialization.

Span-level hints are raw capture material; the backend holds the
authoritative failure taxonomy and cost engine.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from typing import Callable, Optional

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace.status import Status, StatusCode

from ._attributes import (
    OPENINFERENCE_SPAN_KIND,
    SDK_CAPTURE_PROMPTS,
    SDK_ERROR_KIND,
)
from ._config import Config
from ._errors import enrich_error_attributes, is_failed
from ._retries import enrich_retry_attributes, infer_retries
from ._usage import backfill_token_counts, normalize_provider

logger = logging.getLogger(__name__)

_TRUE = "true"
_FALSE = "false"

_MAX_PENDING_TRACES = 1000

# Optional span-kind reclassification hooks (correct AGENT spans the
# instrumentors' heuristics misfire on). Each hook receives the span and
# returns a kind string or None.
_kind_override_hooks: list[Callable[[ReadableSpan], Optional[str]]] = []


def register_span_kind_override(hook: Callable[[ReadableSpan], Optional[str]]) -> None:
    """Register a reclassification hook for instrumentor span kinds."""
    _kind_override_hooks.append(hook)


def _effective_capture(span: ReadableSpan, by_id: dict, global_capture: bool) -> bool:
    seen: set[int] = set()
    current: Optional[ReadableSpan] = span
    while current is not None:
        if current.context is None or current.context.span_id in seen:
            break
        seen.add(current.context.span_id)
        stamp = (current.attributes or {}).get(SDK_CAPTURE_PROMPTS)
        if isinstance(stamp, str):
            return stamp == _TRUE
        if current.parent is None or current.parent.is_remote:
            break
        current = by_id.get(current.parent.span_id)
    return global_capture


def _strip_payload(attributes: dict) -> dict:
    from ._attributes import is_payload_attribute

    return {k: v for k, v in attributes.items() if not is_payload_attribute(k)}


def _copy_span(span: ReadableSpan, attributes: dict, status=None) -> ReadableSpan:
    return ReadableSpan(
        name=span.name,
        context=span.context,
        parent=span.parent,
        resource=span.resource,
        attributes=attributes,
        events=span.events,
        links=span.links,
        kind=span.kind,
        status=status if status is not None else span.status,
        start_time=span.start_time,
        end_time=span.end_time,
        instrumentation_scope=span.instrumentation_scope,
    )


class EnrichingExporter(SpanExporter):
    """Decorator exporter: enrich complete traces, then forward the copies.

    Spans are buffered per trace until the workflow root arrives (children end
    before their parent in the SDK's span model), then the whole trace is
    enriched and forwarded. Buffering is bounded: on overflow the oldest
    pending trace is dropped with a warning (never blocks, never unbounded).
    """

    def __init__(self, config: Config, inner: SpanExporter) -> None:
        self._config = config
        self._inner = inner
        self._by_trace: dict[int, list[ReadableSpan]] = {}
        self._lock = threading.Lock()

    # -- SpanExporter API ------------------------------------------------------

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            ready = self._buffer(spans)
        except Exception:
            logger.exception("SDK enrichment buffering failed; dropping batch")
            return SpanExportResult.FAILURE
        if not ready:
            return SpanExportResult.SUCCESS
        try:
            return self._inner.export(ready)
        except Exception:
            logger.exception("SDK export failed; spans dropped (app unaffected)")
            return SpanExportResult.FAILURE

    def force_flush(self, timeout_millis: Optional[int] = None) -> bool:
        with self._lock:
            ready: list[ReadableSpan] = []
            for trace_id, trace_spans in list(self._by_trace.items()):
                ready.extend(self._process_trace(trace_spans))
            self._by_trace.clear()
        ok = True
        if ready:
            ok = self._inner.export(ready) is SpanExportResult.SUCCESS
        return self._inner.force_flush(timeout_millis) and ok

    def shutdown(self) -> None:
        self.force_flush(timeout_millis=None)
        self._inner.shutdown()

    # -- internals -------------------------------------------------------------

    def _buffer(self, spans: Sequence[ReadableSpan]) -> list[ReadableSpan]:
        with self._lock:
            for span in spans:
                if span.context is None:
                    continue
                self._by_trace.setdefault(span.context.trace_id, []).append(span)
            if len(self._by_trace) > _MAX_PENDING_TRACES:
                dropped = len(self._by_trace) - _MAX_PENDING_TRACES
                for _ in range(dropped):
                    oldest = next(iter(self._by_trace))
                    self._by_trace.pop(oldest)
                logger.warning(
                    "SDK enrichment buffer overflow: dropped %d pending trace(s)",
                    dropped,
                )
            ready: list[ReadableSpan] = []
            for trace_id, trace_spans in list(self._by_trace.items()):
                if self._find_root(trace_spans) is not None:
                    ready.extend(self._process_trace(trace_spans))
                    self._by_trace.pop(trace_id)
            return ready

    @staticmethod
    def _find_root(spans: Sequence[ReadableSpan]) -> Optional[ReadableSpan]:
        for span in spans:
            parent = span.parent
            if parent is None or parent.is_remote:
                return span
        return None

    def _process_trace(self, spans: Sequence[ReadableSpan]) -> list[ReadableSpan]:
        """Enrich one complete trace; returns enriched copies."""
        try:
            return self._enrich(spans)
        except Exception:
            logger.exception("SDK enrichment failed for trace; forwarding spans as-is")
            return list(spans)

    def _enrich(self, spans: Sequence[ReadableSpan]) -> list[ReadableSpan]:
        by_id: dict[int, ReadableSpan] = {}
        for span in spans:
            if span.context is not None:
                by_id[span.context.span_id] = span
        root = self._find_root(spans)

        retry_counts = infer_retries(list(spans))

        processed: dict[int, ReadableSpan] = {}
        for span in spans:
            if span.context is None:
                continue
            attrs = dict(span.attributes or {})

            kind = attrs.get(OPENINFERENCE_SPAN_KIND)
            if kind == "LLM":
                normalize_provider(attrs)
                backfill_token_counts(attrs)

            for hook in _kind_override_hooks:
                try:
                    new_kind = hook(span)
                except Exception:
                    logger.exception("span-kind override hook failed")
                    new_kind = None
                if new_kind:
                    attrs[OPENINFERENCE_SPAN_KIND] = new_kind
                    kind = new_kind

            if is_failed(span) and kind in ("LLM", "TOOL", "RETRIEVER", "CHAIN", "AGENT"):
                attrs = enrich_error_attributes(span, attrs)

            enrich_retry_attributes(
                span, attrs, retry_counts.get(span.context.span_id)
            )

            if not _effective_capture(span, by_id, self._config.capture_prompts):
                attrs = _strip_payload(attrs)

            processed[span.context.span_id] = _copy_span(span, attrs)

        if root is not None and root.context is not None:
            root_copy = processed.get(root.context.span_id)
            if root_copy is not None:
                processed[root.context.span_id] = self._propagate_root_failure(
                    root_copy, list(processed.values())
                )

        return [processed[s.context.span_id] for s in spans if s.context is not None]

    @staticmethod
    def _propagate_root_failure(root: ReadableSpan, spans: Sequence[ReadableSpan]) -> ReadableSpan:
        """Set the workflow root to ERROR when any descendant failed.

        Also stamps ``sdk.error.kind`` with the primary (earliest) failure's
        classification hint, when the root does not already carry one.
        """
        failed = [s for s in spans if s is not root and is_failed(s)]
        if not failed:
            return root
        attrs = dict(root.attributes or {})
        status = root.status
        if status is None or status.status_code != StatusCode.ERROR:
            status = Status(StatusCode.ERROR, description=status.description if status else None)
        if SDK_ERROR_KIND not in attrs:
            earliest = min(failed, key=lambda s: s.start_time or 0)
            kind = (earliest.attributes or {}).get(SDK_ERROR_KIND)
            if isinstance(kind, str):
                attrs[SDK_ERROR_KIND] = kind
        return _copy_span(root, attrs, status)