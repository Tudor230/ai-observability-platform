"""Double-instrumentation guard and re-initialization warnings."""

from __future__ import annotations

import logging

import ai_observability
from ai_observability._instrumentation import (
    _already_instrumented_llamaindex,
    _already_instrumented_langchain,
    uninstrument_frameworks,
)


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