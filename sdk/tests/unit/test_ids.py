"""Deterministic trace-id derivation (Langfuse-style continuation)."""

from __future__ import annotations

import pytest
from opentelemetry import trace as trace_api

from ai_observability._ids import parent_context_for_trace, trace_id_from_seed


def test_trace_id_from_seed_is_deterministic():
    assert trace_id_from_seed("thread-1") == trace_id_from_seed("thread-1")
    assert trace_id_from_seed("thread-1") != trace_id_from_seed("thread-2")


def test_trace_id_from_seed_is_valid_otel_id():
    tid = trace_id_from_seed("thread-1")
    assert 0 < tid < 1 << 128


@pytest.mark.parametrize("seed", ["", "a", "thread-1", "snowflake-id-12345"])
def test_trace_id_from_seed_never_zero(seed):
    assert trace_id_from_seed(seed) != 0


def test_parent_context_pins_trace_id():
    ctx = parent_context_for_trace("thread-1")
    span = trace_api.get_current_span(ctx)
    sc = span.get_span_context()
    assert sc.trace_id == trace_id_from_seed("thread-1")
    assert sc.is_valid
    # The synthetic parent is remote (it does not exist in the trace).
    assert sc.is_remote