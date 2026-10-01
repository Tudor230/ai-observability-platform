"""Raw chromadb client instrumentation: RETRIEVER spans, redaction, failures.

The real ``chromadb`` client runs against an in-memory ``EphemeralClient``
with a deterministic embedding function (``mock_workflows.chroma.fakes``);
no Chroma server and no model download.
"""

from __future__ import annotations

import json

import ai_observability
import pytest
from ai_observability import _instrumentation
from ai_observability._attributes import OPENINFERENCE_SPAN_KIND
from ai_observability._instrumentation import (
    _already_instrumented_chroma,
    uninstrument_frameworks,
)
from mock_workflows.chroma.fakes import (
    BAD_WHERE,
    COLLECTION,
    DOCUMENT_IDS,
    make_collection,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace.status import StatusCode


def _finished(tail):
    ai_observability.flush()
    return list(tail.get_finished_spans())


def _retriever(spans):
    return [
        s
        for s in spans
        if (s.attributes or {}).get(OPENINFERENCE_SPAN_KIND) == "RETRIEVER"
    ]


def _root(spans):
    return next(s for s in spans if s.parent is None or s.parent.is_remote)


def test_init_instruments_the_raw_chromadb_client(tail_exporter):
    assert _already_instrumented_chroma() is True


def test_absent_chromadb_is_skipped_silently(monkeypatch):
    monkeypatch.setattr(_instrumentation, "_chroma_available", lambda: False)
    ai_observability.init(api_key="k", _final_exporter=InMemorySpanExporter())
    assert _already_instrumented_chroma() is False


def test_query_span_carries_kind_input_and_documents(tail_exporter):
    collection = make_collection()
    with ai_observability.workflow(
        name="wf", workflow_id="w-chroma-1", capture_prompts=True
    ):
        collection.query(query_texts=["hardware workstation"], n_results=3)
    spans = _finished(tail_exporter)

    retriever = _retriever(spans)[0]
    attrs = dict(retriever.attributes)
    assert retriever.name == "chroma.query"
    assert retriever.status.status_code == StatusCode.OK
    assert attrs["db.system"] == "chroma"
    assert attrs["db.operation"] == "query"
    assert attrs["db.collection.name"] == COLLECTION
    assert attrs["input.value"] == "hardware workstation"
    assert attrs["input.mime_type"] == "text/plain"
    assert attrs["chroma.query.n_results"] == 3
    assert attrs["chroma.query.result_count"] == 3
    assert attrs["retrieval.documents.0.document.id"] == DOCUMENT_IDS[0]
    assert "workstation" in attrs["retrieval.documents.0.document.content"]
    assert "POL-HW-01" in attrs["retrieval.documents.0.document.metadata"]
    assert isinstance(attrs["retrieval.documents.0.document.score"], float)
    # Generic viewers read output.value (upstream retriever convention).
    assert attrs["output.mime_type"] == "application/json"
    outputs = json.loads(attrs["output.value"])
    assert len(outputs) == 3
    assert outputs[0]["id"] == DOCUMENT_IDS[0]
    assert "workstation" in outputs[0]["content"]
    assert outputs[0]["metadata"]["policy_code"] == "POL-HW-01"
    assert isinstance(outputs[0]["score"], float)
    assert _root(spans).status.status_code == StatusCode.OK


def test_multiple_query_texts_flatten_results_and_use_json_input(tail_exporter):
    collection = make_collection()
    with ai_observability.workflow(
        name="wf", workflow_id="w-chroma-2", capture_prompts=True
    ):
        collection.query(query_texts=["hardware tier", "security keys"], n_results=1)
    attrs = dict(_retriever(_finished(tail_exporter))[0].attributes)
    assert attrs["input.mime_type"] == "application/json"
    assert json.loads(attrs["input.value"]) == ["hardware tier", "security keys"]
    assert attrs["chroma.query.result_count"] == 2
    ids = {
        value
        for key, value in attrs.items()
        if key.endswith(".document.id")
    }
    assert ids == {"POL-HW-01", "POL-SEC-03"}
    outputs = json.loads(attrs["output.value"])
    assert {document["id"] for document in outputs} == {"POL-HW-01", "POL-SEC-03"}


def test_query_error_is_recorded_and_propagates_to_the_root(tail_exporter):
    collection = make_collection()
    with ai_observability.workflow(name="wf", workflow_id="w-chroma-3"):
        with pytest.raises(ValueError):
            collection.query(query_texts=["hardware"], where=BAD_WHERE)
    spans = _finished(tail_exporter)
    retriever = _retriever(spans)[0]
    attrs = dict(retriever.attributes)
    assert retriever.status.status_code == StatusCode.ERROR
    assert attrs["sdk.error.type"] == "ValueError"
    assert any(event.name == "exception" for event in retriever.events)
    # Request-side identity is recorded before the failing call.
    assert attrs["db.collection.name"] == COLLECTION
    assert _root(spans).status.status_code == StatusCode.ERROR


def test_documents_are_redacted_by_default_but_count_survives(tail_exporter):
    collection = make_collection()
    with ai_observability.workflow(name="wf", workflow_id="w-chroma-4"):
        collection.query(query_texts=["secret hardware"], n_results=3)
    attrs = dict(_retriever(_finished(tail_exporter))[0].attributes)
    assert "input.value" not in attrs
    assert "output.value" not in attrs
    assert "retrieval.documents.0.document.id" not in attrs
    assert "retrieval.documents.0.document.content" not in attrs
    assert "retrieval.documents.0.document.metadata" not in attrs
    assert attrs["chroma.query.result_count"] == 3


def test_uninstrumented_collection_produces_no_retriever_span(tail_exporter):
    uninstrument_frameworks()
    collection = make_collection()
    with ai_observability.workflow(
        name="wf", workflow_id="w-chroma-5", capture_prompts=True
    ):
        collection.query(query_texts=["hardware"], n_results=1)
    spans = _finished(tail_exporter)
    assert _retriever(spans) == []
    assert [s.name for s in spans] == ["wf"]
