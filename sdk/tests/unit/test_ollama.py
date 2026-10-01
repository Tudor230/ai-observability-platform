"""Raw ollama client instrumentation: spans, tokens, failures, redaction.

The real ``ollama`` client and the real OpenInference Ollama instrumentor run;
only the HTTP boundary (``Client._request``) is replaced with scripted replies.
"""

from __future__ import annotations

import ollama
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace.status import StatusCode

import ai_observability
from ai_observability import _instrumentation
from ai_observability._attributes import OPENINFERENCE_SPAN_KIND
from ai_observability._instrumentation import (
    _already_instrumented_ollama,
    uninstrument_frameworks,
)
from mock_workflows.ollama.fakes import (
    MODEL,
    MockRateLimitError,
    chat_response,
    patched_ollama,
    stream_chunks,
)


def _finished(tail):
    ai_observability.flush()
    return list(tail.get_finished_spans())


def _llm(spans):
    return [s for s in spans if (s.attributes or {}).get(OPENINFERENCE_SPAN_KIND) == "LLM"]


def _root(spans):
    return next(s for s in spans if s.parent is None or s.parent.is_remote)


def test_init_instruments_the_raw_ollama_client(tail_exporter):
    assert _already_instrumented_ollama() is True


def test_absent_ollama_is_skipped_silently(monkeypatch):
    monkeypatch.setattr(_instrumentation, "_ollama_available", lambda: False)
    ai_observability.init(api_key="k", _final_exporter=InMemorySpanExporter())
    assert _already_instrumented_ollama() is False


def test_chat_span_carries_provider_model_tokens_and_messages(tail_exporter):
    with patched_ollama(chat_response("ok", prompt_tokens=4, completion_tokens=2)):
        with ai_observability.workflow(
            name="wf", workflow_id="w-ollama-1", capture_prompts=True
        ):
            ollama.chat(model=MODEL, messages=[{"role": "user", "content": "hi"}])
    spans = _finished(tail_exporter)
    llm = _llm(spans)[0]
    attrs = dict(llm.attributes)
    assert llm.name == "Chat"
    assert llm.status.status_code == StatusCode.OK
    assert attrs["llm.provider"] == "ollama"
    assert attrs["llm.model_name"] == MODEL
    assert attrs["llm.token_count.prompt"] == 4
    assert attrs["llm.token_count.completion"] == 2
    assert attrs["llm.token_count.total"] == 6
    assert attrs["llm.input_messages.0.message.content"] == "hi"
    assert attrs["llm.output_messages.0.message.content"] == "ok"
    assert _root(spans).status.status_code == StatusCode.OK


def test_chat_error_is_classified_and_propagates_to_the_root(tail_exporter):
    with patched_ollama(MockRateLimitError("429 Too Many Requests")):
        with ai_observability.workflow(name="wf", workflow_id="w-ollama-2"):
            try:
                ollama.chat(model=MODEL, messages=[{"role": "user", "content": "hi"}])
            except MockRateLimitError:
                pass
    spans = _finished(tail_exporter)
    llm = _llm(spans)[0]
    attrs = dict(llm.attributes)
    assert llm.status.status_code == StatusCode.ERROR
    assert attrs["sdk.error.kind"] == "rate_limit"
    assert attrs["llm.model_name"] == MODEL  # recorded request-side
    root = _root(spans)
    assert root.status.status_code == StatusCode.ERROR
    assert dict(root.attributes)["sdk.error.kind"] == "rate_limit"


def test_prompts_are_redacted_by_default_but_tokens_survive(tail_exporter):
    with patched_ollama(chat_response("ok", prompt_tokens=6, completion_tokens=3)):
        with ai_observability.workflow(name="wf", workflow_id="w-ollama-3"):
            ollama.chat(model=MODEL, messages=[{"role": "user", "content": "secret"}])
    attrs = dict(_llm(_finished(tail_exporter))[0].attributes)
    assert "llm.input_messages.0.message.content" not in attrs
    assert "llm.output_messages.0.message.content" not in attrs
    assert attrs["llm.token_count.prompt"] == 6
    assert attrs["llm.token_count.completion"] == 3


def test_streamed_chat_finishes_one_span_with_accumulated_output(tail_exporter):
    chunks = stream_chunks(["Lap", "top"], prompt_tokens=3, completion_tokens=2)
    with patched_ollama(chunks):
        with ai_observability.workflow(
            name="wf", workflow_id="w-ollama-4", capture_prompts=True
        ):
            for _ in ollama.chat(
                model=MODEL,
                messages=[{"role": "user", "content": "hi"}],
                stream=True,
            ):
                pass
    spans = _finished(tail_exporter)
    llm_spans = _llm(spans)
    assert len(llm_spans) == 1
    attrs = dict(llm_spans[0].attributes)
    assert llm_spans[0].status.status_code == StatusCode.OK
    assert attrs["llm.output_messages.0.message.content"] == "Laptop"
    assert attrs["llm.token_count.prompt"] == 3
    assert attrs["llm.token_count.completion"] == 2
    assert attrs["llm.token_count.total"] == 5


def test_uninstrumented_client_produces_no_llm_span(tail_exporter):
    uninstrument_frameworks()
    with patched_ollama(chat_response("ok")):
        with ai_observability.workflow(name="wf", workflow_id="w-ollama-5"):
            ollama.chat(model=MODEL, messages=[{"role": "user", "content": "hi"}])
    spans = _finished(tail_exporter)
    assert _llm(spans) == []
    assert [s.name for s in spans] == ["wf"]
