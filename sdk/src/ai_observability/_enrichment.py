"""Post-end enrichment pipeline (the SDK's export layer).

Instrumentor- and SDK-created spans are enriched as they stream through the
exporter: provider/token normalization, failure hints, retry counts inferred
from failed attempts already seen, workflow-root failure propagation,
prompt-capture redaction, and merging of pending ``sdk.hitl.*`` attributes
recorded during LangGraph interception.

The exporter is **streaming** (F14): it keeps only bounded per-trace
*metadata* (span ids, parents, names, kinds, failure flags) — never the spans
themselves — so a long-running workflow cannot grow SDK memory, and spans
reach the backend while the workflow is still running. Retry inference relies
on the natural ordering (failed attempts end before their successful retry;
children end before their parent); a failure that ends after its retry is not
retroactively counted.

Span-level hints are raw capture material; the backend holds the
authoritative failure taxonomy and cost engine.
"""

from __future__ import annotations

import json
import logging
import threading
from collections import OrderedDict
from collections.abc import Sequence
from contextvars import ContextVar
from dataclasses import dataclass
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
from ._retries import enrich_retry_attributes
from ._state import get_state
from ._usage import backfill_token_counts, normalize_provider

logger = logging.getLogger(__name__)

_TRUE = "true"
_FALSE = "false"

_MAX_PENDING_TRACES = 1000
_MAX_METAS_PER_TRACE = 2000

_RETRYABLE_KINDS = frozenset({"LLM", "TOOL"})
_ERROR_ENRICH_KINDS = frozenset({"LLM", "TOOL", "RETRIEVER", "CHAIN", "AGENT"})

# Optional span-kind reclassification hooks (correct AGENT spans the
# instrumentors' heuristics misfire on). Each hook receives the span and
# returns a kind string or None. Registration is locked and iteration copies
# the list, so registering while the export thread runs is safe (F39).
_kind_override_hooks: list[Callable[[ReadableSpan], Optional[str]]] = []
_hooks_lock = threading.Lock()


def register_span_kind_override(hook: Callable[[ReadableSpan], Optional[str]]) -> None:
    """Register a reclassification hook for instrumentor span kinds."""
    with _hooks_lock:
        _kind_override_hooks.append(hook)


def _snapshot_kind_hooks() -> list[Callable[[ReadableSpan], Optional[str]]]:
    with _hooks_lock:
        return list(_kind_override_hooks)


# Workflow-scoped prompt capture (F14). Children end before their root, so the
# exporter cannot walk parent spans; the workflow boundary publishes the
# setting on the current context instead.
_CAPTURE_CONTEXT: ContextVar[Optional[bool]] = ContextVar(
    "aiobs_capture_prompts", default=None
)


def push_capture_prompts(value: Optional[bool]):
    return _CAPTURE_CONTEXT.set(value)


def reset_capture_prompts(token) -> None:
    _CAPTURE_CONTEXT.reset(token)


def _strip_payload(attributes: dict) -> dict:
    from ._attributes import is_payload_attribute

    return {k: v for k, v in attributes.items() if not is_payload_attribute(k)}


def _langgraph_node(attributes: dict) -> Optional[str]:
    """Extract ``metadata.langgraph_node`` from a CHAIN span, if present."""
    raw = attributes.get(METADATA)
    if not isinstance(raw, str):
        return None
    try:
        parsed = json.loads(raw)
    except ValueError:
        return None
    node = parsed.get("langgraph_node")
    if isinstance(node, (list, tuple)):
        return ".".join(str(part) for part in node)
    if node is None:
        return None
    return str(node)


def _interrupting_node(state: Optional["_TraceState"]) -> Optional[str]:
    """Name of the LangGraph node that interrupted, if derivable.

    Interrupted CHAIN spans carry ``metadata.langgraph_node``; the interrupting
    node is the last one that ran before the graph paused. The node name is
    captured into bounded span metadata at record time, because the streaming
    exporter never retains span payloads.
    """
    if state is None:
        return None
    latest: tuple[int, str] | None = None
    for meta in state.metas.values():
        if meta.kind != "CHAIN" or meta.interrupt_node is None:
            continue
        if latest is None or meta.start_time > latest[0]:
            latest = (meta.start_time, meta.interrupt_node)
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


@dataclass
class _SpanMeta:
    """Bounded per-span metadata used for retry/root inference (no payloads)."""

    span_id: int
    parent_id: Optional[int]
    name: str
    kind: Optional[str]
    failed: bool
    start_time: int
    parent_remote: bool = False
    error_kind: Optional[str] = None
    capture: Optional[bool] = None
    interrupt_node: Optional[str] = None


class _TraceState:
    __slots__ = ("metas", "capture_override")

    def __init__(self) -> None:
        self.metas: "OrderedDict[int, _SpanMeta]" = OrderedDict()
        self.capture_override: Optional[bool] = None


class EnrichingExporter(SpanExporter):
    """Streaming decorator exporter: enrich spans, forward immediately.

    Per-trace state is metadata only, capped per trace and by trace count, so
    memory is bounded regardless of workflow duration.
    """

    def __init__(self, config: Config, inner: SpanExporter) -> None:
        self._config = config
        self._inner = inner
        self._traces: "OrderedDict[int, _TraceState]" = OrderedDict()
        self._lock = threading.Lock()
        # Export health (F13): cumulative counters + the last failure, so an
        # app can detect that telemetry is not reaching the backend.
        self._exported_batches = 0
        self._failed_batches = 0
        self._dropped_traces = 0
        self._last_error: Optional[str] = None

    # -- SpanExporter API ------------------------------------------------------

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            ready = self._enrich_batch(spans)
        except Exception as exc:
            logger.exception("SDK enrichment failed; spans dropped")
            self._record_failure(f"enrichment failed: {exc}")
            return SpanExportResult.FAILURE
        if not ready:
            return SpanExportResult.SUCCESS
        try:
            result = self._inner.export(ready)
        except Exception as exc:
            logger.exception("SDK export failed; spans dropped (app unaffected)")
            self._record_failure(f"{type(exc).__name__}: {exc}")
            return SpanExportResult.FAILURE
        if result is SpanExportResult.SUCCESS:
            with self._lock:
                self._exported_batches += 1
                self._last_error = None
        else:
            self._record_failure("exporter returned FAILURE")
        return result

    def force_flush(self, timeout_millis: Optional[int] = None) -> bool:
        """No spans are buffered; only forward the inner flush (F14)."""
        try:
            return self._inner.force_flush(timeout_millis)
        except Exception:
            logger.exception("SDK flush failed")
            self._record_failure("force_flush failed")
            return False

    def shutdown(self) -> None:
        self._inner.shutdown()

    # -- export health ---------------------------------------------------------

    @property
    def last_export_failed(self) -> bool:
        with self._lock:
            return self._last_error is not None

    def export_stats(self) -> dict:
        with self._lock:
            return {
                "exported_batches": self._exported_batches,
                "failed_batches": self._failed_batches,
                "dropped_traces": self._dropped_traces,
                "last_error": self._last_error,
            }

    def _record_failure(self, message: str) -> None:
        with self._lock:
            self._failed_batches += 1
            self._last_error = message

    # -- enrichment ------------------------------------------------------------

    def _enrich_batch(
        self, spans: Sequence[ReadableSpan]
    ) -> list[ReadableSpan]:
        with self._lock:
            states = self._record(spans)
            context_override = _CAPTURE_CONTEXT.get()
            # Pass 1: per-span enrichment (also records failure kinds in
            # metadata). Pass 2: root propagation, so a root enriched before
            # its failed children still picks up their classification.
            copies = [
                self._enrich_span(span, states.get(span.context.trace_id), context_override)
                for span in spans
                if span.context is not None
            ]
            return [
                self._propagate_root_failure(copy, states.get(copy.context.trace_id))
                for copy in copies
            ]

    def _record(self, spans: Sequence[ReadableSpan]) -> dict[int, _TraceState]:
        states: dict[int, _TraceState] = {}
        for span in spans:
            if span.context is None:
                continue
            trace_id = span.context.trace_id
            state = self._traces.get(trace_id)
            if state is None:
                state = _TraceState()
                self._traces[trace_id] = state
            self._traces.move_to_end(trace_id)
            states[trace_id] = state

        for span in spans:
            if span.context is None:
                continue
            state = states[span.context.trace_id]
            attrs = span.attributes or {}
            kind = attrs.get(OPENINFERENCE_SPAN_KIND)
            parent = span.parent
            meta = _SpanMeta(
                span_id=span.context.span_id,
                parent_id=parent.span_id if parent is not None else None,
                parent_remote=parent.is_remote if parent is not None else False,
                name=span.name or "",
                kind=kind if isinstance(kind, str) else None,
                failed=is_failed(span),
                start_time=span.start_time or 0,
            )
            if kind == "CHAIN":
                meta.interrupt_node = _langgraph_node(attrs)
            stamp = attrs.get(SDK_CAPTURE_PROMPTS)
            if isinstance(stamp, str):
                meta.capture = stamp == _TRUE
            state.metas[meta.span_id] = meta
            while len(state.metas) > _MAX_METAS_PER_TRACE:
                state.metas.popitem(last=False)
            if span.parent is None or span.parent.is_remote:
                if meta.capture is not None:
                    state.capture_override = meta.capture

        while len(self._traces) > _MAX_PENDING_TRACES:
            self._traces.popitem(last=False)
        return states

    def _enrich_span(
        self,
        span: ReadableSpan,
        state: Optional[_TraceState],
        context_override: Optional[bool],
    ) -> ReadableSpan:
        attrs = dict(span.attributes or {})
        kind = attrs.get(OPENINFERENCE_SPAN_KIND)

        if kind == "LLM":
            normalize_provider(attrs)
            backfill_token_counts(attrs)

        for hook in _snapshot_kind_hooks():
            try:
                new_kind = hook(span)
            except Exception:
                logger.exception("span-kind override hook failed")
                new_kind = None
            if new_kind:
                attrs[OPENINFERENCE_SPAN_KIND] = new_kind
                kind = new_kind

        if is_failed(span) and kind in _ERROR_ENRICH_KINDS:
            attrs = enrich_error_attributes(span, attrs)

        enrich_retry_attributes(span, attrs, self._infer_retry(span, state, kind))

        if not self._resolve_capture(span, state, context_override):
            attrs = _strip_payload(attrs)

        if span.context is not None and (span.parent is None or span.parent.is_remote):
            attrs = self._apply_hitl(
                attrs, state, span.context.trace_id, span.context.span_id
            )

        copy = _copy_span(span, attrs)
        if state is not None and span.context is not None:
            meta = state.metas.get(span.context.span_id)
            if meta is not None:
                meta.error_kind = attrs.get(SDK_ERROR_KIND)
        return copy

    def _resolve_capture(
        self,
        span: ReadableSpan,
        state: Optional[_TraceState],
        context_override: Optional[bool],
    ) -> bool:
        if context_override is not None:
            return context_override
        # Walk the metadata tree to the nearest ancestor that set the flag
        # (covers nested workflows whose roots are already known).
        if state is not None and span.context is not None:
            seen: set[int] = set()
            span_id: Optional[int] = span.context.span_id
            while span_id is not None and span_id not in seen:
                seen.add(span_id)
                meta = state.metas.get(span_id)
                if meta is None:
                    break
                if meta.capture is not None:
                    return meta.capture
                span_id = meta.parent_id
        return self._config.capture_prompts

    def _infer_retry(
        self, span: ReadableSpan, state: Optional[_TraceState], kind
    ) -> Optional[int]:
        if state is None or span.context is None or kind not in _RETRYABLE_KINDS:
            return None
        span_id = span.context.span_id
        name = span.name or ""

        # Child-attempt rule: a retried run whose failed children match it.
        children = [
            m
            for m in state.metas.values()
            if m.parent_id == span_id
            and m.kind in _RETRYABLE_KINDS
            and m.name == name
        ]
        failed_children = [m for m in children if m.failed]
        if failed_children and len(failed_children) < len(children):
            return len(failed_children)

        # Sibling-attempt rule: successful span preceded by failed siblings.
        if is_failed(span) or span.parent is None:
            return None
        parent_id = span.parent.span_id
        failed_siblings = [
            m
            for m in state.metas.values()
            if m.parent_id == parent_id
            and m.span_id != span_id
            and m.failed
            and m.kind in _RETRYABLE_KINDS
            and m.name == name
        ]
        return len(failed_siblings) or None

    @staticmethod
    def _apply_hitl(
        attrs: dict,
        state: Optional[_TraceState],
        trace_id: int,
        root_span_id: int,
    ) -> dict:
        """Merge pending sdk.hitl.* attributes recorded for this trace onto the
        workflow root (boundary/lifecycle capture consumed once, first-writer
        wins so existing root attributes are never overwritten).

        ``sdk.hitl.node`` is derived, when missing, from the interrupting
        LangGraph node: the CHAIN span carrying a ``metadata.langgraph_node``
        that ran last (an interrupt pauses the graph, so nothing runs after it).
        """
        pending = get_state().hitl.take((trace_id, root_span_id))
        for key, value in pending.items():
            attrs.setdefault(key, value)
        if attrs.get(SDK_HITL_INTERRUPTED) == "true" and SDK_HITL_NODE not in attrs:
            node = _interrupting_node(state)
            if node is not None:
                attrs[SDK_HITL_NODE] = node
        if attrs.get(SDK_HITL_INTERRUPTED) == "true" and SESSION_ID not in attrs:
            logger.warning(
                "LangGraph HITL interrupt traced without a workflow_id: set "
                "workflow(..., workflow_id=<thread_id>) so the interrupt and "
                "resume runs group into one trace"
            )
        return attrs

    @staticmethod
    def _propagate_root_failure(
        root: ReadableSpan, state: Optional[_TraceState]
    ) -> ReadableSpan:
        """Set the workflow root to ERROR when any descendant has failed.

        Scoped to the root's own subtree: a continued trace (a HITL interrupt
        run next to its resume run) lands sibling roots under one trace id, and
        they must not inherit each other's failures. Also stamps
        ``sdk.error.kind`` with the primary (earliest) failure's classification
        hint when the root does not already carry one.
        """
        if root.parent is not None and not root.parent.is_remote:
            return root
        if state is None or root.context is None:
            return root
        roots = [
            m
            for m in state.metas.values()
            if m.parent_id is None or m.parent_remote
        ]
        if len(roots) <= 1:
            # Single-root trace: every other span belongs to this root.
            failed = [
                m
                for m in state.metas.values()
                if m.failed and m.span_id != root.context.span_id
            ]
        else:
            # Continued trace (HITL interrupt + resume): scope to this root's
            # own subtree so sibling roots don't inherit each other's failures.
            descendant_ids = _descendant_meta_ids(root.context.span_id, state)
            failed = [
                m
                for m in state.metas.values()
                if m.failed and m.span_id in descendant_ids
            ]
        if not failed:
            return root
        attrs = dict(root.attributes or {})
        status = root.status
        if status is None or status.status_code != StatusCode.ERROR:
            status = Status(
                StatusCode.ERROR, description=status.description if status else None
            )
        if SDK_ERROR_KIND not in attrs:
            earliest = min(failed, key=lambda m: m.start_time)
            if earliest.error_kind:
                attrs[SDK_ERROR_KIND] = earliest.error_kind
        return _copy_span(root, attrs, status)


def _descendant_meta_ids(root_span_id: int, state: _TraceState) -> set[int]:
    """Span ids strictly below ``root_span_id`` in the metadata tree.

    Children are metas whose parent points at the current span; parents that
    were never recorded (remote boundaries, evicted metas) end a branch.
    """
    children: dict[Optional[int], list[int]] = {}
    for meta in state.metas.values():
        children.setdefault(meta.parent_id, []).append(meta.span_id)
    found: set[int] = set()
    stack = list(children.get(root_span_id, ()))
    while stack:
        span_id = stack.pop()
        if span_id in found:
            continue
        found.add(span_id)
        stack.extend(children.get(span_id, ()))
    return found
