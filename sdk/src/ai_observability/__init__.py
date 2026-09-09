"""ai_observability — Python observability SDK (phase 1).

Public surface:

    init(...)                 configure + auto-instrument frameworks
    workflow(...)             context manager / decorator (sync + async)
    span(name, context=...)   manual CHAIN span / decorator (sync + async)
    flush()                   force-export pending spans
    shutdown()                flush + tear down the pipeline

``workflow`` and ``span`` accept the same parameters in both forms (context
manager and decorator) and can be used interchangeably. The ``span`` decorator
captures the decorated function's ``input.value`` / ``output.value`` and
records exceptions as span errors.

Env vars (12-factor, explicit init() args override):
    AI_OBSERVABILITY_API_KEY, AI_OBSERVABILITY_ENDPOINT,
    AI_OBSERVABILITY_PROJECT_ID, OTEL_SERVICE_NAME, OTEL_SERVICE_VERSION,
    OTEL_DEPLOYMENT_ENVIRONMENT
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from opentelemetry.sdk.trace.export import SpanExporter

from ._config import Config, resolve_config
from ._instrumentation import instrument_frameworks, uninstrument_frameworks
from ._span import span
from ._state import get_state
from ._tracing import build_provider, register_atexit_flush
from ._workflow import workflow, Workflow

__version__ = "0.1.0"

__all__ = [
    "init",
    "workflow",
    "span",
    "flush",
    "shutdown",
    "Workflow",
    "__version__",
]

logger = logging.getLogger(__name__)


def init(
    *,
    api_key: Optional[str] = None,
    endpoint: Optional[str] = None,
    project_id: Optional[str] = None,
    service_name: Optional[str] = None,
    service_version: Optional[str] = None,
    deployment_environment: Optional[str] = None,
    capture_prompts: bool = False,
    **kwargs: Any,
) -> None:
    """Initialize the SDK: tracing pipeline + framework auto-instrumentation.

    Args override the corresponding env vars. ``capture_prompts`` is opt-in;
    each workflow may override it per-run.
    """
    config = resolve_config(
        {
            "api_key": api_key,
            "endpoint": endpoint,
            "project_id": project_id,
            "service_name": service_name,
            "service_version": service_version,
            "deployment_environment": deployment_environment,
            "capture_prompts": capture_prompts,
        }
    )
    # Internal test hook: swap the final sink (skips the OTLP exporter).
    final_exporter: Optional[SpanExporter] = kwargs.pop("_final_exporter", None)

    state = get_state()
    with state._lock:
        if state.provider is not None:
            logger.warning("SDK already initialized; re-initializing")
            _shutdown_locked()
        provider, enricher = build_provider(config, final_exporter=final_exporter)
        state.config = config
        state.provider = provider
        state.enricher = enricher
    instrument_frameworks(provider)
    register_atexit_flush(provider)


def flush(timeout_millis: Optional[int] = 5000) -> bool:
    """Force-export pending spans (app shutdown / short-lived processes)."""
    state = get_state()
    provider = state.provider
    if provider is None:
        return True
    try:
        return provider.force_flush(timeout_millis=timeout_millis)
    except Exception:
        logger.exception("SDK flush failed")
        return False


def shutdown() -> None:
    """Flush pending spans and tear down the pipeline + instrumentation."""
    state = get_state()
    with state._lock:
        if state.provider is None:
            return
        _shutdown_locked()


def _shutdown_locked() -> None:
    state = get_state()
    try:
        if state.provider is not None:
            state.provider.shutdown()
    except Exception:
        logger.exception("SDK provider shutdown failed")
    state.provider = None
    state.enricher = None
    state.config = None
    uninstrument_frameworks()


def _reset_for_tests() -> None:
    """Internal: full teardown for test isolation."""
    shutdown()


# Re-export for convenient isinstance checks / typing.
Config = Config