"""No duplicate raw-provider spans when a LangChain LLM already traces the call.

``ChatOllama``/``ChatGroq`` invoke the raw provider clients, which the SDK also
instruments. The guard wraps those raw entry points and suppresses them only
while a LangChain LLM run is active; raw calls in chains/tools and outside
LangChain keep their span.
"""

from __future__ import annotations

import ollama
from groq import Groq
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from langchain_ollama import ChatOllama

import ai_observability
from ai_observability._attributes import OPENINFERENCE_SPAN_KIND
from mock_workflows.groq.fakes import chat_completion, patched_groq
from mock_workflows.ollama.fakes import (
    MODEL,
    chat_response,
    patched_ollama,
    stream_chunks,
)


def _finished(exporter):
    ai_observability.flush()
    return list(exporter.get_finished_spans())


def _llm(spans):
    return [
        s
        for s in spans
        if (s.attributes or {}).get(OPENINFERENCE_SPAN_KIND) == "LLM"
    ]


def _names(spans):
    return [s.name for s in spans]


def test_langchain_llm_run_suppresses_the_raw_ollama_span(tail_exporter):
    responses = []

    class RawOllamaChat(FakeListChatModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            response = ollama.chat(
                model=MODEL,
                messages=[{"role": "user", "content": "hi"}],
            )
            responses.append(response.message.content)
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content="ok"))]
            )

    with patched_ollama(chat_response("ok", prompt_tokens=4, completion_tokens=2)):
        with ai_observability.workflow(name="wf", workflow_id="w-dedupe-ollama"):
            RawOllamaChat(responses=["ok"]).invoke("hi")

    assert responses == ["ok"]
    spans = _finished(tail_exporter)
    llm = _llm(spans)
    assert len(llm) == 1
    assert llm[0].name == "RawOllamaChat"
    assert "Chat" not in _names(spans)


def test_real_chatollama_is_traced_once(tail_exporter):
    chunks = stream_chunks(["o", "k"], prompt_tokens=5, completion_tokens=4)
    with patched_ollama(chunks):
        with ai_observability.workflow(name="wf", workflow_id="w-chatollama"):
            result = ChatOllama(model=MODEL).invoke("hi")

    assert result.content == "ok"
    spans = _finished(tail_exporter)
    llm = _llm(spans)
    assert len(llm) == 1
    assert llm[0].name == "ChatOllama"
    assert "Chat" not in _names(spans)


def test_raw_ollama_inside_a_langchain_chain_keeps_its_span(tail_exporter):
    def provider_call(value):
        ollama.chat(
            model=MODEL,
            messages=[{"role": "user", "content": value}],
        )
        return value

    with patched_ollama(chat_response("ok")):
        with ai_observability.workflow(name="wf", workflow_id="w-dedupe-chain"):
            RunnableLambda(provider_call).invoke("hi")

    spans = _finished(tail_exporter)
    assert "Chat" in _names(spans)
    assert "Chat" in [s.name for s in _llm(spans)]


def test_langchain_llm_run_suppresses_the_raw_groq_span(tail_exporter):
    with patched_groq(
        chat_completion("ok", prompt_tokens=3, completion_tokens=2)
    ) as http_client:

        class RawGroqChat(FakeListChatModel):
            def _generate(self, messages, stop=None, run_manager=None, **kwargs):
                Groq(
                    api_key="mock",
                    base_url="http://groq.mock",
                    max_retries=0,
                    http_client=http_client,
                ).chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": "hi"}],
                )
                return ChatResult(
                    generations=[ChatGeneration(message=AIMessage(content="ok"))]
                )

        with ai_observability.workflow(name="wf", workflow_id="w-dedupe-groq"):
            RawGroqChat(responses=["ok"]).invoke("hi")

    spans = _finished(tail_exporter)
    llm = _llm(spans)
    assert len(llm) == 1
    assert llm[0].name == "RawGroqChat"
    assert "Completions" not in _names(spans)
