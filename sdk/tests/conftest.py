"""Shared test fixtures: full SDK teardown/init isolation."""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import ai_observability


@pytest.fixture(autouse=True)
def _sdk_isolation():
    ai_observability._reset_for_tests()
    yield
    ai_observability._reset_for_tests()


@pytest.fixture
def tail_exporter():
    """In-memory tail exporter fed through the SDK's enrichment layer."""
    exporter = InMemorySpanExporter()
    ai_observability.init(
        project_id="proj-1",
        capture_prompts=False,
        _final_exporter=exporter,
    )
    return exporter