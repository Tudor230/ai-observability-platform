"""Pipeline robustness: exporter failures never break the application."""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import ai_observability


class ExplodingExporter:
    """Sink that always raises — must never propagate into app code."""

    def export(self, spans):
        raise RuntimeError("network is down")

    def force_flush(self, timeout_millis=None):
        return True

    def shutdown(self):
        pass


def test_exporter_failure_does_not_break_workflow():
    ai_observability.init(
        project_id="p1",
        capture_prompts=False,
        _final_exporter=ExplodingExporter(),
    )
    # The workflow must complete normally even though export raises.
    with ai_observability.workflow(name="resilient"):
        pass
    assert ai_observability.flush(timeout_millis=1000) in (True, False)


def test_multi_sink_fanout():
    a = InMemorySpanExporter()
    b = InMemorySpanExporter()
    ai_observability.init(
        project_id="p1",
        capture_prompts=False,
        _final_exporter=[a, b],
    )
    with ai_observability.workflow(name="fanout", workflow_id="w-1"):
        pass
    assert ai_observability.flush()
    assert len(a.get_finished_spans()) == 1
    assert len(b.get_finished_spans()) == 1


def test_export_runs_on_background_thread():
    """The batch worker exports on its own thread; the app thread never does
    the network I/O during normal operation (force_flush is explicitly
    synchronous by design)."""
    import threading

    class ThreadRecordingExporter:
        def __init__(self):
            self.export_thread_id = None
            self.exported = threading.Event()

        def export(self, spans):
            self.export_thread_id = threading.get_ident()
            self.exported.set()
            return True

        def force_flush(self, timeout_millis=None):
            return True

        def shutdown(self):
            pass

    exporter = ThreadRecordingExporter()
    ai_observability.init(project_id="p1", _final_exporter=exporter)
    with ai_observability.workflow(name="bg"):
        pass
    # No flush: wait for the BatchSpanProcessor's periodic worker instead.
    assert exporter.exported.wait(timeout=7)
    assert exporter.export_thread_id != threading.get_ident(), (
        "export must not run on the application thread"
    )
    ai_observability.shutdown()