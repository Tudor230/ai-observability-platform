"""Scenario protocol shared by pytest and the CLI runner."""

from __future__ import annotations

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