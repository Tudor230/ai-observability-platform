"""LlamaIndex mock-workflow scenarios.

The LlamaIndex catalog mirrors the LangChain one where the framework's
callback system can express the scenario deterministically. Agent scenarios
are deliberately not included: the 0.14 workflow agents (ReActAgent,
FunctionAgent) run as async workflows that do not play well with MockLLM, so
the agent coverage lives on the LangChain side. Tool coverage is exercised
via ``FunctionTool.call`` (FUNCTION_CALL -> TOOL span).
"""

from __future__ import annotations

from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.tools import FunctionTool

import ai_observability  # noqa: F401
from ..assertions import ScenarioAssertions
from ..scenario import Scenario
from .fakes import (
    FailingRetriever,
    FixedRetriever,
    MockRateLimitError,
    ScriptedMockLLM,
)

WORKFLOW = dict(
    name="order-status",
    client_id="client-42",
    workflow_id="order-123",
    version="v2",
    context={"channel": "web"},
)


def _rag_engine(llm) -> RetrieverQueryEngine:
    return RetrieverQueryEngine.from_args(
        retriever=FixedRetriever(),
        llm=llm,
    )


def run_happy_path() -> None:
    llm = ScriptedMockLLM(
        responses=["order 123 is shipped"],
        prompt_tokens=6,
        completion_tokens=4,
    )
    engine = _rag_engine(llm)
    with ai_observability.workflow(**WORKFLOW, capture_prompts=True):
        engine.query("what is the status of order 123?")


def assert_happy_path(spans) -> list[str]:
    checks = ScenarioAssertions(spans)
    root = checks.require_single_root("order-status")
    if root is None:
        return checks.failures
    checks.attr_eq(root, "sdk.project_id", "proj-1")
    checks.attr_eq(root, "sdk.client_id", "client-42")
    checks.attr_eq(root, "sdk.workflow_id", "order-123")
    checks.attr_eq(root, "session.id", "order-123")
    checks.status_ok(root)

    retrievers = checks.spans(kind="RETRIEVER")
    checks.require(len(retrievers) >= 1, "expected at least one RETRIEVER span")
    documented = [
        s for s in retrievers
        if "retrieval.documents.0.document.id" in checks.attrs(s)
    ]
    checks.require(len(documented) >= 1, "expected retrieval documents on a RETRIEVER span")
    if documented:
        checks.attr_eq(documented[0], "retrieval.documents.0.document.id", "doc-1")
        checks.attr_eq(documented[0], "retrieval.documents.0.document.content", "order 123 is shipped")

    llm_spans = checks.spans(kind="LLM")
    exact = [
        s for s in llm_spans
        if checks.attrs(s).get("llm.token_count.prompt") == 6
    ]
    checks.require(len(exact) >= 1, "expected an LLM span with prompt=6 tokens")
    if exact:
        checks.attr_eq(exact[0], "llm.token_count.completion", 4)
        checks.attr_eq(exact[0], "llm.token_count.total", 10)
        checks.descendant_of(exact[0], root)
    checks.require(len(checks.spans(kind="CHAIN")) >= 2, "expected CHAIN spans for the query engine")
    return checks.failures


def run_llm_error() -> None:
    llm = ScriptedMockLLM(
        responses=["unused"],
        prompt_tokens=0,
        completion_tokens=0,
        fail_budget=1,
        fail_exception=lambda: ValueError("llm exploded"),
    )
    with ai_observability.workflow(**WORKFLOW):
        try:
            llm.complete("hello")
        except ValueError:
            pass


def assert_llm_error(spans) -> list[str]:
    checks = ScenarioAssertions(spans)
    root = checks.require_single_root("order-status")
    if root is None:
        return checks.failures
    llm = checks.require_span(kind="LLM")
    if llm is not None:
        checks.status_error(llm)
        checks.attr_contains(llm, "sdk.error.type", "ValueError")
        checks.attr_eq(llm, "sdk.error.kind", "provider_error")
    checks.status_error(root)
    return checks.failures


def run_rate_limit() -> None:
    llm = ScriptedMockLLM(
        responses=["unused"],
        prompt_tokens=0,
        completion_tokens=0,
        fail_budget=1,
        fail_exception=lambda: MockRateLimitError("429 Too Many Requests"),
    )
    with ai_observability.workflow(**WORKFLOW):
        try:
            llm.complete("hello")
        except MockRateLimitError:
            pass


def assert_rate_limit(spans) -> list[str]:
    checks = ScenarioAssertions(spans)
    root = checks.require_single_root("order-status")
    if root is None:
        return checks.failures
    llm = checks.require_span(kind="LLM")
    if llm is not None:
        checks.status_error(llm)
        checks.attr_eq(llm, "sdk.error.kind", "rate_limit")
    checks.status_error(root)
    checks.attr_eq(root, "sdk.error.kind", "rate_limit")
    return checks.failures


def run_retrieval_failure() -> None:
    llm = ScriptedMockLLM(
        responses=["unused"],
        prompt_tokens=0,
        completion_tokens=0,
    )
    engine = RetrieverQueryEngine.from_args(retriever=FailingRetriever(), llm=llm)
    with ai_observability.workflow(**WORKFLOW):
        try:
            engine.query("status?")
        except RuntimeError:
            pass


def assert_retrieval_failure(spans) -> list[str]:
    checks = ScenarioAssertions(spans)
    root = checks.require_single_root("order-status")
    if root is None:
        return checks.failures
    retrievers = checks.spans(kind="RETRIEVER")
    checks.require(len(retrievers) >= 1, "expected at least one RETRIEVER span")
    failed = [s for s in retrievers if checks.status_is_error(s)]
    checks.require(len(failed) >= 1, "expected a failed RETRIEVER span")
    if failed:
        checks.attr_contains(failed[0], "sdk.error.type", "RuntimeError")
    checks.status_error(root)
    return checks.failures


def run_high_latency() -> None:
    llm = ScriptedMockLLM(
        responses=["slow answer"],
        prompt_tokens=8,
        completion_tokens=3,
        sleep=0.2,
    )
    with ai_observability.workflow(**WORKFLOW):
        llm.complete("please be slow")


def assert_high_latency(spans) -> list[str]:
    checks = ScenarioAssertions(spans)
    root = checks.require_single_root("order-status")
    if root is None:
        return checks.failures
    llm = checks.require_span(kind="LLM")
    if llm is not None and llm.start_time is not None and llm.end_time is not None:
        duration_ms = (llm.end_time - llm.start_time) / 1e6
        checks.require(duration_ms >= 150, f"LLM span too fast: {duration_ms:.0f}ms")
    checks.status_ok(root)
    return checks.failures


def run_tool_call() -> None:
    def lookup_stock(symbol: str) -> str:
        """Look up a stock price."""
        return f"{symbol}=42"

    tool = FunctionTool.from_defaults(fn=lookup_stock)
    with ai_observability.workflow(**WORKFLOW):
        tool.call({"symbol": "TSLA"})


def assert_tool_call(spans) -> list[str]:
    checks = ScenarioAssertions(spans)
    root = checks.require_single_root("order-status")
    if root is None:
        return checks.failures
    tool_span = checks.require_span(kind="TOOL")
    if tool_span is not None:
        checks.attr_eq(tool_span, "tool.name", "lookup_stock")
        checks.parent_is(tool_span, root)
        checks.status_ok(tool_span)
    checks.status_ok(root)
    return checks.failures


SCENARIOS: list[Scenario] = [
    Scenario(
        id="li_happy_path",
        framework="llamaindex",
        description="RAG query engine: CHAIN + RETRIEVER (documents) + LLM, fixed tokens",
        run=run_happy_path,
        assert_trace=assert_happy_path,
    ),
    Scenario(
        id="li_llm_error",
        framework="llamaindex",
        description="LLM call fails: ERROR span, exception event, provider_error hint",
        run=run_llm_error,
        assert_trace=assert_llm_error,
    ),
    Scenario(
        id="li_rate_limit",
        framework="llamaindex",
        description="429-style error: rate_limit hint on LLM span + workflow root",
        run=run_rate_limit,
        assert_trace=assert_rate_limit,
    ),
    Scenario(
        id="li_retrieval_failure",
        framework="llamaindex",
        description="retriever fails: RETRIEVER ERROR span + exception event",
        run=run_retrieval_failure,
        assert_trace=assert_retrieval_failure,
    ),
    Scenario(
        id="li_high_latency",
        framework="llamaindex",
        description="controlled fake sleep makes latency visible on the LLM span",
        run=run_high_latency,
        assert_trace=assert_high_latency,
    ),
    Scenario(
        id="li_tool_call",
        framework="llamaindex",
        description="FunctionTool call: TOOL span with name + parameters",
        run=run_tool_call,
        assert_trace=assert_tool_call,
    ),
]