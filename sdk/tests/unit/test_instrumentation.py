"""Double-instrumentation guard, optional-framework skips, and init resilience."""

from __future__ import annotations

import logging

import ai_observability
from ai_observability import _instrumentation
from ai_observability._instrumentation import (
    _already_instrumented_chroma,
    _already_instrumented_groq,
    _already_instrumented_langchain,
    _already_instrumented_llamaindex,
    _already_instrumented_ollama,
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
        assert _already_instrumented_ollama() is True
        assert _already_instrumented_groq() is True
        assert _already_instrumented_chroma() is True


def test_uninstrument_clears_guards():
    ai_observability.init(project_id="p1", _final_exporter=None)
    assert _already_instrumented_langchain() is True
    assert _already_instrumented_llamaindex() is True
    assert _already_instrumented_ollama() is True
    assert _already_instrumented_groq() is True
    assert _already_instrumented_chroma() is True
    uninstrument_frameworks()
    assert _already_instrumented_langchain() is False
    assert _already_instrumented_llamaindex() is False
    assert _already_instrumented_ollama() is False
    assert _already_instrumented_groq() is False
    assert _already_instrumented_chroma() is False


def test_langgraph_guard_after_init():
    ai_observability.init(project_id="p1", _final_exporter=None)
    assert _already_instrumented_langgraph() is True


def test_langgraph_guard_cleared_on_uninstrument():
    ai_observability.init(project_id="p1", _final_exporter=None)
    assert _already_instrumented_langgraph() is True
    uninstrument_frameworks()
    assert _already_instrumented_langgraph() is False


def test_absent_frameworks_are_skipped_quietly(monkeypatch, caplog):
    """A missing optional framework is a debug skip, not an error (only the
    ollama absence was covered before the unified policy)."""
    monkeypatch.setattr(_instrumentation, "_langchain_available", lambda: False)
    monkeypatch.setattr(_instrumentation, "_llamaindex_available", lambda: False)
    monkeypatch.setattr(_instrumentation, "_chroma_available", lambda: False)
    monkeypatch.setattr(_instrumentation, "_groq_available", lambda: False)
    with caplog.at_level(logging.DEBUG):
        ai_observability.init(api_key="k", _final_exporter=None)
    assert _already_instrumented_langchain() is False
    assert _already_instrumented_llamaindex() is False
    assert _already_instrumented_chroma() is False
    assert _already_instrumented_groq() is False
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert not [r for r in caplog.records if "DependencyConflict" in r.getMessage()]


def test_instrumentor_failure_never_breaks_init(monkeypatch, caplog):
    """A raising instrumentor is skipped with a warning; init() and the other
    instrumentors are unaffected (plan §8)."""
    from openinference.instrumentation.langchain import LangChainInstrumentor

    def boom(self, **kwargs):
        raise RuntimeError("instrumentor exploded")

    monkeypatch.setattr(LangChainInstrumentor, "instrument", boom)
    with caplog.at_level(logging.WARNING):
        ai_observability.init(api_key="k", _final_exporter=None)
    assert _already_instrumented_langchain() is False
    assert _already_instrumented_ollama() is True
    assert any(
        "LangChainInstrumentor failed" in record.getMessage()
        for record in caplog.records
    )