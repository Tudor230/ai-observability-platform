"""Post-end enrichment pipeline (the SDK's export layer).

Instrumentor- and SDK-created spans are immutable once ended, yet the SDK
must retroactively stamp ``sdk.error.*``/``sdk.retry.*`` attributes, fill
providers and token counts, propagate failures to the workflow root, enforce
prompt-capture redaction, and merge pending ``sdk.hitl.*`` attributes recorded
during LangGraph interception. All of that happens here: a decorator
``SpanExporter`` between the BatchSpanProcessor and the OTLP exporter that
deep-copies each trace's spans and stamps the copies before serialization.

Span-level hints are raw capture material; the backend holds the
authoritative failure taxonomy and cost engine.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Sequence
from typing import Callable, Optional

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace.status import Status, StatusCode

from ._attributes import (
    METADATA,
    OPENINFERENCE_SPAN_KIND,
    SDK_CAPTURE_PROMPTS,
    SDK_ERROR_KIND,
    SDK_HITL_INTERRUPTED,
    SDK_HITL_NODE,
    SESSION_ID,
)
from ._config import Config
from ._errors import enrich_error_attributes, is_failed
from ._retries import enrich_retry_attributes, infer_retries
from ._state import get_state
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


def _interrupting_node(spans: Sequence[ReadableSpan]) -> Optional[str]:
    """Name of the LangGraph node that interrupted, if derivable.

    Interrupted CHAIN spans carry ``metadata.langgraph_node``; the interrupting
    node is the last one that ran before the graph paused.
    """
    latest: tuple[int, str] | None = None
    for span in spans:
        attrs = span.attributes or {}
        if attrs.get(OPENINFERENCE_SPAN_KIND) != "CHAIN":
            continue
        raw = attrs.get(METADATA)
        if not isinstance(raw, str):
            continue
        try:
            parsed = json.loads(raw)
        except ValueError:
            continue
        node = parsed.get("langgraph_node")
        if node is None:
            continue
        if isinstance(node, (list, tuple)):
            node = ".".join(str(part) for part in node)
        if latest is None or (span.start_time or 0) > latest[0]:
            latest = ((span.start_time or 0), str(node))
    return latest[1] if latest is not None else None


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

        # A trace may have several roots: trace-id continuation (a LangGraph
        # HITL interrupt and its resume share one trace id) lands multiple
        # workflow roots in one export batch. Each root is enriched and its
        # failure status is scoped to its own descendants.
        all_processed = list(processed.values())
        for root in spans:
            if root.context is None:
                continue
            if root.parent is not None and not root.parent.is_remote:
                continue
            root_copy = processed.get(root.context.span_id)
            if root_copy is None:
                continue
            root_copy = self._apply_hitl(root_copy, all_processed)
            processed[root.context.span_id] = self._propagate_root_failure(
                root_copy, all_processed
            )

        return [processed[s.context.span_id] for s in spans if s.context is not None]

    @staticmethod
    def _apply_hitl(root: ReadableSpan, spans: Sequence[ReadableSpan]) -> ReadableSpan:
        """Merge pending sdk.hitl.* attributes recorded for this trace onto the
        workflow root (boundary/lifecycle capture consumed once, first-writer
        wins so existing root attributes are never overwritten).

        ``sdk.hitl.node`` is derived, when missing, from the interrupting
        LangGraph node: the CHAIN span carrying a ``metadata.langgraph_node``
        that ran last (an interrupt pauses the graph, so nothing runs after it).
        """
        if root.context is None:
            return root
        pending = get_state().hitl.take(
            (root.context.trace_id, root.context.span_id)
        )
        attrs = dict(root.attributes or {})
        for key, value in pending.items():
            attrs.setdefault(key, value)
        if attrs.get(SDK_HITL_INTERRUPTED) == "true" and SDK_HITL_NODE not in attrs:
            node = _interrupting_node(spans)
            if node is not None:
                attrs[SDK_HITL_NODE] = node
        if attrs.get(SDK_HITL_INTERRUPTED) == "true" and SESSION_ID not in attrs:
            logger.warning(
                "LangGraph HITL interrupt traced without a workflow_id: set "
                "workflow(..., workflow_id=<thread_id>) so the interrupt and "
                "resume runs group into one trace"
            )
        if not pending and SDK_HITL_NODE not in attrs:
            return root
        return _copy_span(root, attrs)

    @staticmethod
    def _propagate_root_failure(root: ReadableSpan, spans: Sequence[ReadableSpan]) -> ReadableSpan:
        """Set the workflow root to ERROR when any descendant failed.

        Scoped to the root's own subtree, so sibling roots in a continued trace
        (a HITL interrupt run next to its resume run) do not inherit each
        other's failures. Also stamps ``sdk.error.kind`` with the primary
        (earliest) failure's classification hint, when the root does not
        already carry one.
        """
        by_id: dict[int, ReadableSpan] = {}
        for span in spans:
            if span.context is not None:
                by_id[span.context.span_id] = span
        roots = [
            s for s in spans
            if s.context is not None
            and (s.parent is None or s.parent.is_remote)
        ]
        if len(roots) <= 1:
            # Single-root trace: every other span belongs to this root.
            descendant_ids = {
                s.context.span_id for s in spans if s.context is not None
            }
            descendant_ids.discard(root.context.span_id)
        else:
            # Continued trace (HITL interrupt + resume): scope to this root's
            # own subtree so sibling roots don't inherit each other's failures.
            descendant_ids = _descendant_span_ids(root, by_id)
        failed = [
            s for s in spans
            if s is not root
            and s.context is not None
            and s.context.span_id in descendant_ids
            and is_failed(s)
        ]
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


def _descendant_span_ids(root: ReadableSpan, by_id: dict[int, ReadableSpan]) -> set[int]:
    """Span ids strictly below ``root`` in the span tree (non-remote links).

    Children are spans whose parent points at the current span; remote parents
    are boundaries (they are roots of their own subtree), so traversal stops.
    """
    if root.context is None:
        return set()
    found: set[int] = set()
    stack: list[ReadableSpan] = []
    for span in by_id.values():
        parent = span.parent
        if (
            span.context is not None
            and parent is not None
            and not parent.is_remote
            and parent.span_id == root.context.span_id
        ):
            stack.append(span)
    while stack:
        current = stack.pop()
        if current.context is None or current.context.span_id in found:
            continue
        found.add(current.context.span_id)
        for span in by_id.values():
            parent = span.parent
            if (
                span.context is not None
                and parent is not None
                and not parent.is_remote
                and parent.span_id == current.context.span_id
            ):
                stack.append(span)
    return found