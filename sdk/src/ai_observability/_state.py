"""Process-global SDK state: config, provider, enricher, instrumentation marks.

Kept intentionally small; everything else derives from the provider pipeline.
"""

from __future__ import annotations

import threading
from typing import Optional

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import get_tracer as api_get_tracer

from ._config import Config


class _SDKState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.config: Optional[Config] = None
        self.provider: Optional[TracerProvider] = None
        self.enricher: Optional["EnrichingExporter"] = None  # noqa: F821

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