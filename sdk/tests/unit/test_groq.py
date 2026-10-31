"""Raw groq client instrumentation: spans, tokens, failures, redaction.

The real ``groq`` client and the real OpenInference Groq instrumentor run; only
the HTTP boundary is replaced with scripted responses (``patched_groq``).
"""

from __future__ import annotations

from typing import TypedDict

import pytest
from groq import Groq, RateLimitError
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace.status import StatusCode

import ai_observability
from ai_observability import _instrumentation
from ai_observability._attributes import OPENINFERENCE_SPAN_KIND
from ai_observability._instrumentation import (
    _already_instrumented_groq,
    uninstrument_frameworks,
)
from mock_workflows.groq.fakes import (
    MODEL,
    chat_completion,
    patched_groq,
    rate_limit_response,
)


def _finished(tail):
    ai_observability.flush()
    return list(tail.get_finished_spans())


def _llm(spans):
    return [s for s in spans if (s.attributes or {}).get(OPENINFERENCE_SPAN_KIND) == "LLM"]


def _root(spans):
    return next(s for s in spans if s.parent is None or s.parent.is_remote)


def _chat(http_client):
    return Groq(
        api_key="mock",
        base_url="http://groq.mock",
        max_retries=0,
        http_client=http_client,
    ).chat.completions.create(
        model=MODEL,
        temperature=0,
        messages=[{"role": "user", "content": "hi"}],
    )


def test_init_instruments_the_raw_groq_client(tail_exporter):
    assert _already_instrumented_groq() is True


def test_absent_groq_is_skipped_silently(monkeypatch):
    monkeypatch.setattr(_instrumentation, "_groq_available", lambda: False)
    ai_observability.init(api_key="k", _final_exporter=InMemorySpanExporter())
    assert _already_instrumented_groq() is False


def test_chat_span_carries_provider_model_tokens_and_messages(tail_exporter):
    with patched_groq(chat_completion("ok", prompt_tokens=4, completion_tokens=2)) as http_client:
        with ai_observability.workflow(
            name="wf", workflow_id="w-groq-1", capture_prompts=True
        ):
            _chat(http_client)
    spans = _finished(tail_exporter)
    llm = _llm(spans)[0]
    attrs = dict(llm.attributes)
    assert llm.name == "Completions"
    assert llm.status.status_code == StatusCode.OK
    assert attrs["llm.provider"] == "groq"
    assert attrs["llm.model_name"] == MODEL
    assert attrs["llm.token_count.prompt"] == 4
    assert attrs["llm.token_count.completion"] == 2
    assert attrs["llm.token_count.total"] == 6
    assert attrs["llm.input_messages.0.message.content"] == "hi"
    assert attrs["llm.output_messages.0.message.content"] == "ok"
    # No LangChain run is active, so the workflow root remains the parent.
    assert llm.parent.span_id == _root(spans).context.span_id
    assert _root(spans).status.status_code == StatusCode.OK


def test_rate_limit_is_classified_and_propagates_to_the_root(tail_exporter):
    with patched_groq(rate_limit_response()) as http_client:
        with ai_observability.workflow(name="wf", workflow_id="w-groq-2"):
            try:
                _chat(http_client)
            except RateLimitError:
                pass
    spans = _finished(tail_exporter)
    llm = _llm(spans)[0]
    attrs = dict(llm.attributes)
    assert llm.status.status_code == StatusCode.ERROR
    assert attrs["sdk.error.type"] == "groq.RateLimitError"
    assert attrs["sdk.error.kind"] == "rate_limit"
    assert attrs["llm.provider"] == "groq"
    root = _root(spans)
    assert root.status.status_code == StatusCode.ERROR
    assert dict(root.attributes)["sdk.error.kind"] == "rate_limit"


def test_prompts_are_redacted_by_default_but_tokens_survive(tail_exporter):
    with patched_groq(chat_completion("ok", prompt_tokens=6, completion_tokens=3)) as http_client:
        with ai_observability.workflow(name="wf", workflow_id="w-groq-3"):
            _chat(http_client)
    attrs = dict(_llm(_finished(tail_exporter))[0].attributes)
    assert "input.value" not in attrs
    assert "output.value" not in attrs
    assert "llm.input_messages.0.message.content" not in attrs
    assert "llm.output_messages.0.message.content" not in attrs
    assert attrs["llm.token_count.prompt"] == 6
    assert attrs["llm.token_count.completion"] == 3


@pytest.mark.asyncio
async def test_chat_nests_under_active_langgraph_node(tail_exporter):
    from langgraph.graph import END, START, StateGraph

    class _State(TypedDict):
        value: int

    with patched_groq(
        chat_completion("ok", prompt_tokens=4, completion_tokens=2)
    ) as http_client:
        def call_llm(state: _State):
            _chat(http_client)
            return {"value": state["value"] + 1}

        graph = (
            StateGraph(_State)
            .add_node("call_llm", call_llm)
            .add_edge(START, "call_llm")
            .add_edge("call_llm", END)
            .compile()
        )
        with ai_observability.workflow(name="wf", workflow_id="w-groq-5"):
            # Mirror an app-owned wrapper span: the node span must still win
            # over the ambient wrapper for the raw provider call.
            with ai_observability.span("rca.investigation"):
                await graph.ainvoke({"value": 0})

    spans = _finished(tail_exporter)
    node_span = next(span for span in spans if span.name == "call_llm")
    llm = _llm(spans)[0]
    assert llm.parent is not None
    assert llm.parent.span_id == node_span.context.span_id


def test_uninstrumented_client_produces_no_llm_span(tail_exporter):
    uninstrument_frameworks()
    with patched_groq(chat_completion("ok")) as http_client:
        with ai_observability.workflow(name="wf", workflow_id="w-groq-4"):
            _chat(http_client)
    spans = _finished(tail_exporter)
    assert _llm(spans) == []
    assert [s.name for s in spans] == ["wf"]
