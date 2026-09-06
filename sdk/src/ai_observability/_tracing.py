"""Tracing pipeline ownership: provider, batching, export, flush/shutdown.

Reliability guarantees (plan §8): wrapper/instrumentor exceptions never
propagate; export runs on background threads; queue overflow drops spans with
a warning; export/ingest failures are logged, never raised.
"""

from __future__ import annotations

import atexit
import logging
from typing import Optional

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SpanExportResult,
    SpanExporter,
)

from ._config import Config
from ._enrichment import EnrichingExporter

logger = logging.getLogger(__name__)

SERVICE_NAME = "service.name"
SERVICE_VERSION = "service.version"
DEPLOYMENT_ENVIRONMENT = "deployment.environment"

_PROJECT_HEADER = "x-project-name"


class _FanOutExporter(SpanExporter):
    """Minimal fan-out (FanOutSpanExporter was removed from recent SDKs)."""

    def __init__(self, exporters: list[SpanExporter]) -> None:
        self._exporters = exporters

    def export(self, spans) -> SpanExportResult:
        results = []
        for exporter in self._exporters:
            try:
                results.append(exporter.export(spans))
            except Exception:
                logger.exception("fan-out exporter failed")
                results.append(SpanExportResult.FAILURE)
        return (
            SpanExportResult.SUCCESS
            if all(r is SpanExportResult.SUCCESS for r in results)
            else SpanExportResult.FAILURE
        )

    def force_flush(self, timeout_millis=None) -> bool:
        results = []
        for exporter in self._exporters:
            try:
                results.append(exporter.force_flush(timeout_millis))
            except Exception:
                logger.exception("fan-out exporter flush failed")
                results.append(False)
        return all(results)

    def shutdown(self) -> None:
        for exporter in self._exporters:
            try:
                exporter.shutdown()
            except Exception:
                logger.exception("fan-out exporter shutdown failed")


def build_headers(config: Config) -> dict[str, str]:
    """Custom OTLP headers: the platform's ingest authenticates and routes by
    these. Phoenix reads ``x-project-name`` for project routing (>=15.5.0)."""
    headers: dict[str, str] = {}
    if config.api_key:
        headers["authorization"] = f"Bearer {config.api_key}"
    if config.project_id:
        headers[_PROJECT_HEADER] = config.project_id
    return headers


def build_otlp_exporter(config: Config) -> OTLPSpanExporter:
    """The OTLP HTTP exporter the SDK owns (endpoint + routing headers)."""
    endpoint = f"{config.endpoint}/v1/traces" if config.endpoint else None
    return OTLPSpanExporter(
        endpoint=endpoint,
        headers=build_headers(config) or None,
    )


def build_resource(config: Config) -> Resource:
    attributes: dict = {SERVICE_NAME: config.service_name}
    if config.service_version:
        attributes[SERVICE_VERSION] = config.service_version
    if config.deployment_environment:
        attributes[DEPLOYMENT_ENVIRONMENT] = config.deployment_environment
    return Resource.create(attributes)


def build_provider(
    config: Config, final_exporter: Optional[SpanExporter] = None
) -> tuple[TracerProvider, EnrichingExporter]:
    """Create the SDK-owned provider. ``final_exporter`` overrides the OTLP
    sink (test hook); the enrichment layer always runs in front of it. A
    list/tuple of exporters is fanned out (used by the mock-workflow CLI to
    assert locally and export over OTLP at the same time)."""
    resource = build_resource(config)
    provider = TracerProvider(resource=resource)

    inner: SpanExporter
    if final_exporter is None:
        inner = build_otlp_exporter(config)
    elif isinstance(final_exporter, (list, tuple)):
        inner = _FanOutExporter(list(final_exporter))
    else:
        inner = final_exporter

    enricher = EnrichingExporter(config, inner)
    processor = BatchSpanProcessor(span_exporter=enricher)
    provider.add_span_processor(processor)
    return provider, enricher


_atexit_registered = False


def register_atexit_flush(provider: TracerProvider) -> None:
    global _atexit_registered
    if _atexit_registered:
        return

    def _flush_on_exit() -> None:
        try:
            provider.force_flush(timeout_millis=5_000)
        except Exception:
            logger.exception("SDK atexit flush failed")

    atexit.register(_flush_on_exit)
    _atexit_registered = True