"""Double-instrumentation guard and re-initialization warnings."""

from __future__ import annotations

import logging

import ai_observability
from ai_observability._instrumentation import (
    _already_instrumented_llamaindex,
    _already_instrumented_langchain,
    uninstrument_frameworks,
)
from ai_observability._langgraph import _already_instrumented_langgraph


def test_double_instrumentation_is_detected(caplog):
    ai_observability.init(project_id="p1", _final_exporter=None)
    # instrument() is only called from init(); simulate a second external
    # instrumentor by re-checking the guard.
    with caplog.at_level(logging.WARNING):
        assert _already_instrumented_langchain() is True
        assert _already_instrumented_llamaindex() is True


def test_uninstrument_clears_guards():
    ai_observability.init(project_id="p1", _final_exporter=None)
    assert _already_instrumented_langchain() is True
    assert _already_instrumented_llamaindex() is True
    uninstrument_frameworks()
    assert _already_instrumented_langchain() is False
    assert _already_instrumented_llamaindex() is False


def test_langgraph_guard_after_init():
    ai_observability.init(project_id="p1", _final_exporter=None)
    assert _already_instrumented_langgraph() is True


def test_langgraph_guard_cleared_on_uninstrument():
    ai_observability.init(project_id="p1", _final_exporter=None)
    assert _already_instrumented_langgraph() is True
    uninstrument_frameworks()
    assert _already_instrumented_langgraph() is False