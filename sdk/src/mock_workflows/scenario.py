"""Scenario protocol shared by pytest and the CLI runner."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable

from opentelemetry.sdk.trace import ReadableSpan


@dataclass(frozen=True)
class Scenario:
    id: str
    framework: str
    description: str
    run: Callable[[], object]
    assert_trace: Callable[[list[ReadableSpan]], list[str]]


@dataclass
class ScenarioResult:
    scenario: Scenario
    failures: list[str]
    error: str | None = None
    span_count: int = 0

    @property
    def passed(self) -> bool:
        return not self.failures and self.error is None


def scenario_with_random_workflow_id(
    scenario_id: str,
    framework: str,
    description: str,
    run: Callable[[str], object],
    assert_trace: Callable[[list[ReadableSpan], str], list[str]],
    workflow_id_base: str,
) -> Scenario:
    """Build a scenario whose run and assertions share one random workflow id.

    The id is generated once per Scenario, so every scenario run derives its
    own deterministic trace id (workflow_id seeds the trace id) and the backend
    keeps each scenario as its own execution instead of replacing one another.
    """
    workflow_id = f"{workflow_id_base}-{uuid.uuid4().hex[:8]}"
    return Scenario(
        id=scenario_id,
        framework=framework,
        description=description,
        run=lambda: run(workflow_id=workflow_id),
        assert_trace=lambda spans: assert_trace(spans, workflow_id=workflow_id),
    )
