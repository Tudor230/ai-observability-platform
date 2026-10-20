"""Databricks AI Search instrumentation: RETRIEVER spans, redaction, failures.

The fake index mirrors the canonical ``databricks.ai_search`` result shape
(``manifest.columns`` + ``result.data_array``) so no Databricks workspace or
network access is required.
"""

from __future__ import annotations

import json
from typing import Any, TypedDict

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace.status import StatusCode

import ai_observability
from ai_observability import _databricks, _instrumentation
from ai_observability._attributes import OPENINFERENCE_SPAN_KIND
from ai_observability._state import get_state

RESPONSE = {
    "manifest": {
        "columns": [
            {"name": "id"},
            {"name": "text"},
            {"name": "severity"},
            {"name": "score"},
        ]
    },
    "result": {
        "row_count": 2,
        "data_array": [
            ["ke-1", "database timeout", "high", 0.91],
            ["ke-2", "authentication failed", "medium", 0.82],
        ],
    },
}


class FakeIndex:
    name = "cat.sch.kedb_index"
    endpoint_name = "kedb-endpoint"

    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response = RESPONSE if response is None else response
        self.error = error

    def similarity_search(
        self,
        columns,
        query_text=None,
        query_vector=None,
        filters=None,
        num_results=5,
        query_type=None,
        score_threshold=None,
        **kwargs,
    ):
        if self.error is not None:
            raise self.error
        return self.response


class FakeAsyncIndex(FakeIndex):
    async def similarity_search(
        self,
        columns,
        query_text=None,
        query_vector=None,
        filters=None,
        num_results=5,
        query_type=None,
        score_threshold=None,
        **kwargs,
    ):
        if self.error is not None:
            raise self.error
        return self.response


@pytest.fixture
def databricks_instrumented(tail_exporter, monkeypatch):
    monkeypatch.setattr(
        _databricks, "_index_classes", lambda: [FakeIndex, FakeAsyncIndex]
    )
    _databricks.instrument_databricks(get_state().provider)
    yield
    _databricks.uninstrument_databricks()


def _finished(tail):
    ai_observability.flush()
    return list(tail.get_finished_spans())


def _retriever(spans):
    return [
        span
        for span in spans
        if (span.attributes or {}).get(OPENINFERENCE_SPAN_KIND) == "RETRIEVER"
    ]


def _root(spans):
    return next(span for span in spans if span.parent is None or span.parent.is_remote)


def test_query_span_carries_index_query_and_documents(
    databricks_instrumented, tail_exporter
):
    with ai_observability.workflow(
        name="wf", workflow_id="w-dbx-1", capture_prompts=True
    ):
        FakeIndex().similarity_search(
            columns=["id", "text", "severity", "score"],
            query_text="database timeout",
            num_results=3,
            query_type="HYBRID",
            filters={"status": "open"},
        )
    spans = _finished(tail_exporter)
    retriever = _retriever(spans)[0]
    attrs = dict(retriever.attributes)

    assert retriever.name == "databricks.ai_search.query"
    assert retriever.status.status_code == StatusCode.OK
    assert retriever.parent.span_id == _root(spans).context.span_id
    assert attrs["db.system"] == "databricks"
    assert attrs["db.operation"] == "query"
    assert attrs["db.collection.name"] == FakeIndex.name
    assert attrs["databricks.ai_search.endpoint"] == FakeIndex.endpoint_name
    assert attrs["input.value"] == "database timeout"
    assert attrs["input.mime_type"] == "text/plain"
    assert attrs["databricks.ai_search.query_type"] == "HYBRID"
    assert attrs["databricks.ai_search.num_results"] == 3
    assert attrs["databricks.ai_search.result_count"] == 2
    assert json.loads(attrs["databricks.ai_search.columns"]) == [
        "id",
        "text",
        "severity",
        "score",
    ]
    assert json.loads(attrs["databricks.ai_search.filters"]) == {"status": "open"}
    assert attrs["retrieval.documents.0.document.id"] == "ke-1"
    assert attrs["retrieval.documents.0.document.content"] == "database timeout"
    assert json.loads(attrs["retrieval.documents.0.document.metadata"]) == {
        "severity": "high"
    }
    assert attrs["retrieval.documents.0.document.score"] == 0.91
    assert attrs["retrieval.documents.1.document.id"] == "ke-2"
    outputs = json.loads(attrs["output.value"])
    assert [document["id"] for document in outputs] == ["ke-1", "ke-2"]
    assert outputs[0]["metadata"] == {"severity": "high"}


def test_query_vector_only_records_dimension(databricks_instrumented, tail_exporter):
    with ai_observability.workflow(
        name="wf", workflow_id="w-dbx-2", capture_prompts=True
    ):
        FakeIndex().similarity_search(columns=["id"], query_vector=[0.1, 0.2, 0.3])
    attrs = dict(_retriever(_finished(tail_exporter))[0].attributes)
    assert attrs["databricks.ai_search.query_vector_dimension"] == 3
    assert "input.value" not in attrs
    assert attrs["databricks.ai_search.result_count"] == 2


def test_documents_are_redacted_by_default_but_count_survives(
    databricks_instrumented, tail_exporter
):
    with ai_observability.workflow(name="wf", workflow_id="w-dbx-3"):
        FakeIndex().similarity_search(
            columns=["id", "text", "severity", "score"],
            query_text="database timeout",
            num_results=3,
            query_type="HYBRID",
        )
    attrs = dict(_retriever(_finished(tail_exporter))[0].attributes)
    assert "input.value" not in attrs
    assert "output.value" not in attrs
    assert "retrieval.documents.0.document.id" not in attrs
    assert "retrieval.documents.0.document.content" not in attrs
    assert "retrieval.documents.0.document.metadata" not in attrs
    assert attrs["databricks.ai_search.result_count"] == 2
    assert attrs["databricks.ai_search.query_type"] == "HYBRID"


def test_query_error_is_recorded_and_propagates_to_the_root(
    databricks_instrumented, tail_exporter
):
    error = RuntimeError("ai search unavailable")
    with (
        ai_observability.workflow(name="wf", workflow_id="w-dbx-4"),
        pytest.raises(RuntimeError),
    ):
        FakeIndex(error=error).similarity_search(
            columns=["id"], query_text="database"
        )
    spans = _finished(tail_exporter)
    retriever = _retriever(spans)[0]
    attrs = dict(retriever.attributes)
    assert retriever.status.status_code == StatusCode.ERROR
    assert attrs["sdk.error.type"] == "RuntimeError"
    assert any(event.name == "exception" for event in retriever.events)
    assert _root(spans).status.status_code == StatusCode.ERROR


@pytest.mark.asyncio
async def test_async_query_emits_retriever(databricks_instrumented, tail_exporter):
    with ai_observability.workflow(
        name="wf", workflow_id="w-dbx-5", capture_prompts=True
    ):
        await FakeAsyncIndex().similarity_search(
            columns=["id", "text", "severity", "score"],
            query_text="async lookup",
            num_results=2,
        )
    attrs = dict(_retriever(_finished(tail_exporter))[0].attributes)
    assert attrs["input.value"] == "async lookup"
    assert attrs["databricks.ai_search.result_count"] == 2


@pytest.mark.asyncio
async def test_query_nests_under_active_langgraph_node(
    databricks_instrumented, tail_exporter
):
    from langgraph.graph import END, START, StateGraph

    class _State(TypedDict):
        value: int

    def search(state: _State):
        FakeIndex().similarity_search(
            columns=["id", "text", "severity", "score"], query_text="find known error"
        )
        return {"value": state["value"] + 1}

    graph = (
        StateGraph(_State)
        .add_node("search", search)
        .add_edge(START, "search")
        .add_edge("search", END)
        .compile()
    )
    with ai_observability.workflow(
        name="wf", workflow_id="w-dbx-6", capture_prompts=True
    ):
        await graph.ainvoke({"value": 0})

    spans = _finished(tail_exporter)
    node_span = next(span for span in spans if span.name == "search")
    retriever = _retriever(spans)[0]
    assert retriever.parent is not None
    assert retriever.parent.span_id == node_span.context.span_id


def test_init_instruments_databricks_when_available(monkeypatch):
    exporter = InMemorySpanExporter()
    monkeypatch.setattr(_databricks, "_index_classes", lambda: [FakeIndex])
    monkeypatch.setattr(_instrumentation, "_databricks_available", lambda: True)

    ai_observability.init(api_key="k", _final_exporter=exporter)
    with ai_observability.workflow(name="wf", workflow_id="w-dbx-7"):
        FakeIndex().similarity_search(columns=["id"], query_text="init wiring")
    ai_observability.flush()

    assert _retriever(list(exporter.get_finished_spans()))
