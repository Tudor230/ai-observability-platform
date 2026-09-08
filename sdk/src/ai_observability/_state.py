"""Process-global SDK state: config, provider, enricher, instrumentation marks.

Kept intentionally small; everything else derives from the provider pipeline.
"""

from __future__ import annotations

import threading
from typing import Optional

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import get_tracer as api_get_tracer

from ._config import Config

_MAX_PENDING_HITL_TRACES = 1000


class HITLRegistry:
    """Bounded, lock-guarded store of pending human-in-the-loop attributes.

    Keyed by OTel ``trace_id``: LangGraph interception (the boundary patch and
    the lifecycle hook) records ``sdk.hitl.*`` values here while the workflow
    root span is still open; the enrichment layer consumes them with ``take``
    when the trace completes. First writer wins per key; on overflow the oldest
    entries are evicted (never blocks, never unbounded).
    """

    def __init__(self, max_entries: int = _MAX_PENDING_HITL_TRACES) -> None:
        self._lock = threading.Lock()
        self._max_entries = max_entries
        self._by_trace: dict[int, dict[str, str]] = {}

    def record(self, trace_id: int, **attrs: str) -> None:
        if not attrs:
            return
        with self._lock:
            entry = self._by_trace.setdefault(trace_id, {})
            for key, value in attrs.items():
                if value is not None:
                    entry.setdefault(key, value)
            overflow = len(self._by_trace) - self._max_entries
            if overflow > 0:
                for stale in list(self._by_trace)[:overflow]:
                    self._by_trace.pop(stale)

    def take(self, trace_id: int) -> dict[str, str]:
        with self._lock:
            return self._by_trace.pop(trace_id, {})

    def clear(self) -> None:
        with self._lock:
            self._by_trace.clear()


class _SDKState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.config: Optional[Config] = None
        self.provider: Optional[TracerProvider] = None
        self.enricher: Optional["EnrichingExporter"] = None  # noqa: F821
        self.hitl = HITLRegistry()

    def get_tracer(self, name: str = "ai_observability"):
        with self._lock:
            if self.provider is not None:
                return self.provider.get_tracer(name)
        # Not initialized: fall back to the global provider (no-op tracer when
        # nothing is configured) so workflow()/span() never raise.
        return api_get_tracer(name)


_state = _SDKState()


def get_state() -> _SDKState:
    return _state