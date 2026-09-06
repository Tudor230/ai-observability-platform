"""Scenario regression suite: every mock workflow through the real SDK."""

from __future__ import annotations

import pytest

from mock_workflows import SCENARIOS
from mock_workflows.runner import run_scenario


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.id for s in SCENARIOS])
def test_scenario(scenario, tail_exporter):
    result = run_scenario(scenario, tail_exporter)
    detail = "\n".join(f"  - {f}" for f in result.failures) if result.failures else "ok"
    assert result.passed, f"scenario {scenario.id} failed:\n{detail}"