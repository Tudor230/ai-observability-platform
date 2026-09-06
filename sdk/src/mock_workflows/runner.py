"""Mock-workflow harness: run scenarios through the real SDK and assert the
exported (enriched) OTLP spans. Shared by pytest and the CLI runner.
"""

from __future__ import annotations

import logging

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from ai_observability import flush

from .langchain.scenarios import SCENARIOS as LANGCHAIN_SCENARIOS
from .llamaindex.scenarios import SCENARIOS as LLAMAINDEX_SCENARIOS
from .scenario import Scenario, ScenarioResult

logger = logging.getLogger(__name__)

SCENARIOS: list[Scenario] = LANGCHAIN_SCENARIOS + LLAMAINDEX_SCENARIOS


def run_scenario(scenario: Scenario, tail: InMemorySpanExporter) -> ScenarioResult:
    """Run one scenario against the SDK's in-memory tail exporter."""
    tail.clear()
    error: str | None = None
    try:
        scenario.run()
    except Exception as exc:  # noqa: BLE001 — scenario errors are reported
        error = f"{type(exc).__name__}: {exc}"
        logger.exception("scenario %s raised", scenario.id)
    try:
        flush(timeout_millis=10_000)
    except Exception:
        logger.exception("flush failed for scenario %s", scenario.id)
    spans = list(tail.get_finished_spans())
    failures = scenario.assert_trace(spans) if not error else [f"scenario raised: {error}"]
    return ScenarioResult(
        scenario=scenario,
        failures=failures or [],
        error=error,
        span_count=len(spans),
    )


def run_all(tail: InMemorySpanExporter) -> list[ScenarioResult]:
    return [run_scenario(scenario, tail) for scenario in SCENARIOS]