"""Export health (F13): failures are visible and flush() no longer lies."""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace.export import SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import ai_observability


class FailingExporter:
    def export(self, spans):
        return SpanExportResult.FAILURE

    def force_flush(self, timeout_millis=None):
        return True

    def shutdown(self):
        pass


def _run(name: str = "wf") -> None:
    with ai_observability.workflow(name=name, workflow_id="w-1"):
        pass


def test_failed_export_is_reported_and_flush_returns_false():
    ai_observability.init(project_id="p1", _final_exporter=FailingExporter())
    try:
        _run()
        assert ai_observability.flush(timeout_millis=2000) is False
        stats = ai_observability.export_stats()
        assert stats["failed_batches"] >= 1
        assert stats["last_error"]
    finally:
        ai_observability._reset_for_tests()


def test_successful_export_clears_last_error_and_flush_is_true():
    sink = InMemorySpanExporter()
    ai_observability.init(project_id="p1", _final_exporter=sink)
    try:
        _run("ok")
        assert ai_observability.flush(timeout_millis=2000) is True
        stats = ai_observability.export_stats()
        assert stats["exported_batches"] >= 1
        assert stats["last_error"] is None
        assert len(sink.get_finished_spans()) == 1
    finally:
        ai_observability._reset_for_tests()


def test_unknown_init_kwargs_raise_type_error():
    with pytest.raises(TypeError):
        ai_observability.init(project="typo")


def test_traces_endpoint_is_not_duplicated():
    from ai_observability._tracing import traces_endpoint

    assert traces_endpoint("http://localhost:6006") == "http://localhost:6006/v1/traces"
    assert (
        traces_endpoint("http://localhost:6006/v1/traces")
        == "http://localhost:6006/v1/traces"
    )
    assert traces_endpoint("http://localhost:6006/") == "http://localhost:6006/v1/traces"
    assert traces_endpoint(None) is None
