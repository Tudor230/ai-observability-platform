"""LangChain mock-workflow scenarios (the full failure catalog, plan §9.2).

Each scenario runs through the real SDK + OpenInference LangChain instrumentor
with framework-native fake models producing fixed responses and fixed usage.
Assertions are programmatic (trace shape, attributes, failure propagation) —
no golden files.
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import tool

import ai_observability  # noqa: F401  (SDK must be initialized by runner)
from ..assertions import ScenarioAssertions
from ..scenario import Scenario
from .fakes import (
    MockRateLimitError,
    MockTimeoutError,
    ScriptedChatModel,
    ai_message,
    tool_calling_message,
)

WORKFLOW = dict(
    name="checkout",
    client_id="client-42",
    workflow_id="order-123",
    version="v2",
    context={"channel": "web", "ticket_id": "INC-12345"},
)


def _build_agent(model) -> RunnableLambda:
    """A manual agent loop as a runnable named *agent* (AGENT kind via the
    instrumentor's run-name heuristic). Passing ``config`` threads LangChain
    callbacks so inner LLM/TOOL runs nest under the agent span."""

    @tool
    def lookup_stock(symbol: str) -> str:
        """Look up a stock price."""
        return f"{symbol}=42"

    def agent_loop(query: str, config: dict | None = None):
        step = model.invoke([HumanMessage(content=query)], config=config)
        for call in step.tool_calls:
            lookup_stock.invoke({"symbol": call["args"]["symbol"]}, config=config)
        return model.invoke([HumanMessage(content="finalize")], config=config)

    return RunnableLambda(agent_loop).with_config({"run_name": "checkout_agent"})


def run_happy_path() -> None:
    model = ScriptedChatModel(
        responses=[
            tool_calling_message("lookup_stock", {"symbol": "TSLA"}, 5, 9),
            ai_message("TSLA is $42.00", 3, 4),
        ]
    )
    agent = _build_agent(model)
    with ai_observability.workflow(**WORKFLOW, capture_prompts=True):
        agent.invoke("what is the price of TSLA?")
    return model


def assert_happy_path(spans) -> list[str]:
    checks = ScenarioAssertions(spans)
    root = checks.require_single_root("checkout")
    if root is None:
        return checks.failures
    checks.attr_eq(root, "sdk.project_id", "proj-1")
    checks.attr_eq(root, "sdk.client_id", "client-42")
    checks.attr_eq(root, "sdk.workflow_id", "order-123")
    checks.attr_eq(root, "session.id", "order-123")
    checks.attr_eq(root, "sdk.workflow.version", "v2")
    checks.attr_eq(root, "metadata", json.dumps(WORKFLOW["context"]))
    checks.status_ok(root)

    agent = checks.require_span(kind="AGENT", name="checkout_agent")
    checks.parent_is(agent, root)

    llm_spans = checks.spans(kind="LLM")
    checks.require(len(llm_spans) == 2, f"expected 2 LLM spans, got {len(llm_spans)}")
    for llm in llm_spans:
        checks.parent_is(llm, agent)
        checks.attr_is_int(llm, "llm.token_count.prompt")
        checks.attr_is_int(llm, "llm.token_count.completion")
        checks.attr_is_int(llm, "llm.token_count.total")
    if len(llm_spans) == 2:
        checks.attr_eq(llm_spans[0], "llm.token_count.prompt", 5)
        checks.attr_eq(llm_spans[0], "llm.token_count.completion", 9)
        checks.attr_eq(llm_spans[1], "llm.token_count.prompt", 3)
        checks.attr_eq(llm_spans[1], "llm.token_count.completion", 4)

    tool_spans = checks.spans(kind="TOOL")
    checks.require(len(tool_spans) == 1, f"expected 1 TOOL span, got {len(tool_spans)}")
    if tool_spans:
        checks.parent_is(tool_spans[0], agent)
        checks.attr_eq(tool_spans[0], "tool.name", "lookup_stock")
        checks.status_ok(tool_spans[0])
    if llm_spans:
        checks.attr_eq(
            llm_spans[0],
            "llm.input_messages.0.message.content",
            "what is the price of TSLA?",
        )
        checks.attr_eq(llm_spans[1], "llm.output_messages.0.message.content", "TSLA is $42.00")
    return checks.failures


def run_llm_error() -> None:
    model = ScriptedChatModel(
        responses=[ai_message("unused", 0, 0)],
        fail_budget=1,
        fail_exception=lambda: ValueError("model exploded"),
    )
    with ai_observability.workflow(**WORKFLOW):
        try:
            model.invoke("hello")
        except ValueError:
            pass


def assert_llm_error(spans) -> list[str]:
    checks = ScenarioAssertions(spans)
    root = checks.require_single_root("checkout")
    if root is None:
        return checks.failures
    llm = checks.require_span(kind="LLM")
    if llm is not None:
        checks.status_error(llm)
        checks.attr_contains(llm, "sdk.error.type", "ValueError")
        checks.attr_eq(llm, "sdk.error.message", "model exploded")
        checks.attr_eq(llm, "sdk.error.kind", "provider_error")
        checks.require(checks.has_exception_event(llm), "LLM span missing exception event")
    checks.status_error(root)
    return checks.failures


def run_tool_timeout() -> None:
    state = {"calls": 0}

    @tool
    def flaky_tool(query: str) -> str:
        """A tool that times out on the first attempt."""
        state["calls"] += 1
        if state["calls"] == 1:
            time.sleep(0.05)
            raise MockTimeoutError("tool timed out after 50ms")
        return "recovered"

    retrying_tool = flaky_tool.with_retry(stop_after_attempt=3)
    with ai_observability.workflow(**WORKFLOW):
        retrying_tool.invoke({"query": "q"})


def assert_tool_timeout(spans) -> list[str]:
    checks = ScenarioAssertions(spans)
    root = checks.require_single_root("checkout")
    if root is None:
        return checks.failures
    tool_spans = checks.spans(kind="TOOL")
    checks.require(len(tool_spans) == 2, f"expected 2 TOOL attempts, got {len(tool_spans)}")
    failed = [s for s in tool_spans if checks.status_is_error(s)]
    ok = [s for s in tool_spans if not checks.status_is_error(s)]
    checks.require(len(failed) == 1, "expected exactly 1 failed TOOL attempt")
    checks.require(len(ok) == 1, "expected exactly 1 successful TOOL attempt")
    if failed:
        checks.attr_eq(failed[0], "sdk.error.kind", "timeout")
    if ok:
        checks.attr_eq(ok[0], "sdk.retry.count", 1)
    checks.status_error(root)
    checks.attr_eq(root, "sdk.error.kind", "timeout")
    return checks.failures


def run_invalid_json() -> None:
    model = FakeMessagesListChatModel(
        responses=[ai_message("not valid json {[", 3, 2)]
    )
    step = RunnableLambda(lambda text: json.loads(text)).with_config(
        {"run_name": "parse_structured_output"}
    )

    def flow(query: str, config: dict | None = None):
        raw = model.invoke([HumanMessage(content=query)], config=config)
        return step.invoke(raw.content, config=config)

    runnable = RunnableLambda(flow).with_config({"run_name": "structured_checkout"})
    with ai_observability.workflow(**WORKFLOW):
        try:
            runnable.invoke("book order")
        except json.JSONDecodeError:
            pass


def assert_invalid_json(spans) -> list[str]:
    checks = ScenarioAssertions(spans)
    root = checks.require_single_root("checkout")
    if root is None:
        return checks.failures
    failed = checks.spans(kind="CHAIN")
    parse_steps = [s for s in failed if s.name == "parse_structured_output"]
    checks.require(len(parse_steps) == 1, "expected the structured-output CHAIN span")
    if parse_steps:
        checks.status_error(parse_steps[0])
        checks.attr_eq(parse_steps[0], "sdk.error.kind", "invalid_output")
    checks.status_error(root)
    return checks.failures


class FailingRetriever(BaseRetriever):
    """Retriever that always fails (deterministic retrieval failure)."""

    def _get_relevant_documents(self, query, *, run_manager=None):
        raise RuntimeError("vector store unavailable")


def run_retrieval_failure() -> None:
    retriever = FailingRetriever()

    def flow(query: str, config: dict | None = None):
        return retriever.invoke(query, config=config)

    runnable = RunnableLambda(flow).with_config({"run_name": "rag_checkout"})
    with ai_observability.workflow(**WORKFLOW):
        try:
            runnable.invoke("what is order status?")
        except RuntimeError:
            pass


def assert_retrieval_failure(spans) -> list[str]:
    checks = ScenarioAssertions(spans)
    root = checks.require_single_root("checkout")
    if root is None:
        return checks.failures
    retriever_span = checks.require_span(kind="RETRIEVER")
    if retriever_span is not None:
        checks.status_error(retriever_span)
        checks.attr_contains(retriever_span, "sdk.error.type", "RuntimeError")
    checks.status_error(root)
    return checks.failures


def run_high_latency() -> None:
    model = ScriptedChatModel(
        responses=[ai_message("slow answer", 10, 5)],
        sleep=0.2,
    )
    with ai_observability.workflow(**WORKFLOW):
        model.invoke("please be slow")


def assert_high_latency(spans) -> list[str]:
    checks = ScenarioAssertions(spans)
    root = checks.require_single_root("checkout")
    if root is None:
        return checks.failures
    llm = checks.require_span(kind="LLM")
    if llm is not None and llm.start_time is not None and llm.end_time is not None:
        duration_ms = (llm.end_time - llm.start_time) / 1e6
        checks.require(duration_ms >= 150, f"LLM span too fast: {duration_ms:.0f}ms")
    checks.status_ok(root)
    return checks.failures


def run_rate_limit() -> None:
    model = ScriptedChatModel(
        responses=[ai_message("unused", 0, 0)],
        fail_budget=1,
        fail_exception=lambda: MockRateLimitError("429 Too Many Requests"),
    )
    with ai_observability.workflow(**WORKFLOW):
        try:
            model.invoke("hello")
        except MockRateLimitError:
            pass


def assert_rate_limit(spans) -> list[str]:
    checks = ScenarioAssertions(spans)
    root = checks.require_single_root("checkout")
    if root is None:
        return checks.failures
    llm = checks.require_span(kind="LLM")
    if llm is not None:
        checks.status_error(llm)
        checks.attr_eq(llm, "sdk.error.kind", "rate_limit")
    checks.status_error(root)
    checks.attr_eq(root, "sdk.error.kind", "rate_limit")
    return checks.failures


def run_retry_then_success() -> None:
    model = ScriptedChatModel(
        responses=[ai_message("finally ok", 4, 3)],
        fail_budget=2,
        fail_exception=lambda: MockTimeoutError("transient failure"),
    )
    retrying = model.with_retry(stop_after_attempt=3)
    with ai_observability.workflow(**WORKFLOW):
        retrying.invoke("hello")


def assert_retry_then_success(spans) -> list[str]:
    checks = ScenarioAssertions(spans)
    root = checks.require_single_root("checkout")
    if root is None:
        return checks.failures
    llm_spans = checks.spans(kind="LLM")
    failed = [s for s in llm_spans if checks.status_is_error(s)]
    ok = [s for s in llm_spans if not checks.status_is_error(s)]
    checks.require(len(failed) == 2, f"expected 2 failed attempts, got {len(failed)}")
    checks.require(len(ok) >= 1, f"expected >=1 successful attempt, got {len(ok)}")
    if failed:
        checks.attr_eq(failed[0], "sdk.error.kind", "timeout")
    if ok:
        checks.attr_eq(ok[-1], "sdk.retry.count", 2)
    checks.status_error(root)
    return checks.failures


SCENARIOS: list[Scenario] = [
    Scenario(
        id="lc_happy_path",
        framework="langchain",
        description="checkout agent: AGENT span with nested LLM + TOOL calls, fixed tokens",
        run=run_happy_path,
        assert_trace=assert_happy_path,
    ),
    Scenario(
        id="lc_llm_error",
        framework="langchain",
        description="LLM call fails: ERROR span, exception event, provider_error hint",
        run=run_llm_error,
        assert_trace=assert_llm_error,
    ),
    Scenario(
        id="lc_tool_timeout",
        framework="langchain",
        description="tool times out then retries: TOOL ERROR + sdk.retry.count=1",
        run=run_tool_timeout,
        assert_trace=assert_tool_timeout,
    ),
    Scenario(
        id="lc_invalid_json",
        framework="langchain",
        description="structured-output step returns invalid JSON: invalid_output hint",
        run=run_invalid_json,
        assert_trace=assert_invalid_json,
    ),
    Scenario(
        id="lc_retrieval_failure",
        framework="langchain",
        description="retriever fails: RETRIEVER ERROR span + exception event",
        run=run_retrieval_failure,
        assert_trace=assert_retrieval_failure,
    ),
    Scenario(
        id="lc_high_latency",
        framework="langchain",
        description="controlled fake sleep makes latency visible on the LLM span",
        run=run_high_latency,
        assert_trace=assert_high_latency,
    ),
    Scenario(
        id="lc_rate_limit",
        framework="langchain",
        description="429-style error: rate_limit hint on LLM span + workflow root",
        run=run_rate_limit,
        assert_trace=assert_rate_limit,
    ),
    Scenario(
        id="lc_retry_then_success",
        framework="langchain",
        description="with_retry succeeds on attempt 3: sdk.retry.count=2",
        run=run_retry_then_success,
        assert_trace=assert_retry_then_success,
    ),
]