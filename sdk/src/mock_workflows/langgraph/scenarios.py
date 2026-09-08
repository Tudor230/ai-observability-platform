"""LangGraph mock-workflow scenarios (HITL capture, plan §9.2).

Each scenario runs through the real SDK + OpenInference LangChain instrumentor
+ the SDK's LangGraph auto-interception (boundary patch + lifecycle hook) with
deterministic graphs (no LLM, no network). Assertions are programmatic: trace
shape, ``sdk.hitl.*`` attributes, interrupt-not-error semantics, and thread
correlation.
"""

from __future__ import annotations

import json
from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

import ai_observability  # noqa: F401  (SDK must be initialized by runner)
from ..assertions import ScenarioAssertions
from ..scenario import Scenario

WORKFLOW = dict(
    name="approval",
    client_id="client-42",
    workflow_id="thread-1",
    version="v1",
    context={"channel": "web"},
)

INTERRUPT_PAYLOAD = {"question": "Approve refund?", "amount": 42}


class _State(TypedDict):
    messages: list[str]


def _build_approval_graph():
    def human_review(state: _State):
        decision = interrupt(INTERRUPT_PAYLOAD)
        return {"messages": state["messages"] + [f"decided:{decision}"]}

    return (
        StateGraph(_State)
        .add_node("human_review", human_review)
        .add_edge(START, "human_review")
        .add_edge("human_review", END)
        .compile(checkpointer=InMemorySaver())
    )


def _build_linear_graph():
    def node_a(state: _State):
        return {"messages": state["messages"] + ["a"]}

    def node_b(state: _State):
        return {"messages": state["messages"] + ["b"]}

    return (
        StateGraph(_State)
        .add_node("node_a", node_a)
        .add_node("node_b", node_b)
        .add_edge(START, "node_a")
        .add_edge("node_a", "node_b")
        .add_edge("node_b", END)
        .compile()
    )


# --- scenarios ----------------------------------------------------------------


def run_basic() -> None:
    graph = _build_linear_graph()
    with ai_observability.workflow(
        name="checkout", client_id="client-42", workflow_id="order-1"
    ):
        graph.invoke({"messages": []})


def assert_basic(spans) -> list[str]:
    checks = ScenarioAssertions(spans)
    root = checks.require_single_root("checkout")
    if root is None:
        return checks.failures
    checks.status_ok(root)
    for node in ("node_a", "node_b"):
        found = checks.spans(kind="CHAIN", name=node)
        checks.require(len(found) == 1, f"expected exactly 1 CHAIN span named {node}")
        if found:
            checks.descendant_of(found[0], root)
            meta = checks.metadata_json(found[0]) or {}
            checks.require(
                meta.get("langgraph_node") == node,
                f"{node} span missing metadata.langgraph_node",
            )
    return checks.failures


def run_hitl_interrupt() -> None:
    graph = _build_approval_graph()
    with ai_observability.workflow(**WORKFLOW):
        graph.invoke(
            {"messages": []},
            config={"configurable": {"thread_id": WORKFLOW["workflow_id"]}},
        )


def assert_hitl_interrupt(spans) -> list[str]:
    checks = ScenarioAssertions(spans)
    root = checks.require_single_root("approval")
    if root is None:
        return checks.failures
    checks.status_ok(root)
    checks.attr_eq(root, "sdk.hitl.interrupted", "true")
    checks.attr_eq(root, "sdk.hitl.thread_id", "thread-1")
    checks.attr_eq(root, "sdk.hitl.node", "human_review")
    payload = dict(root.attributes or {}).get("sdk.hitl.interrupt_payload")
    checks.require(
        isinstance(payload, str) and json.loads(payload) == [INTERRUPT_PAYLOAD],
        f"sdk.hitl.interrupt_payload mismatch: {payload!r}",
    )
    checks.require(
        "sdk.error.kind" not in dict(root.attributes or {}),
        "an interrupt must not be flagged as an error",
    )
    node = checks.require_span(kind="CHAIN", name="human_review")
    if node is not None:
        checks.status_ok(node)
    return checks.failures


def run_hitl_resume() -> None:
    graph = _build_approval_graph()
    config = {"configurable": {"thread_id": WORKFLOW["workflow_id"]}}
    with ai_observability.workflow(**WORKFLOW):
        graph.invoke({"messages": []}, config=config)
    with ai_observability.workflow(**WORKFLOW):
        graph.invoke(Command(resume=True), config=config)


def assert_hitl_resume(spans) -> list[str]:
    checks = ScenarioAssertions(spans)
    roots = [s for s in spans if s.parent is None or s.parent.is_remote]
    checks.require(
        len(roots) == 2,
        f"expected 2 roots (interrupt + resume), got {len(roots)}",
    )
    checks.require(
        len({r.context.trace_id for r in roots}) == 1,
        "interrupt and resume must continue the SAME trace (deterministic "
        "trace-id from workflow_id/thread_id)",
    )
    resume = next(
        (r for r in roots if (r.attributes or {}).get("sdk.hitl.resume_value") is not None),
        None,
    )
    checks.require(resume is not None, "no resume trace found")
    if resume is None:
        return checks.failures
    checks.status_ok(resume)
    checks.attr_eq(resume, "sdk.hitl.interrupted", "false")
    checks.attr_eq(resume, "sdk.hitl.resumed", "true")
    checks.attr_eq(resume, "sdk.hitl.thread_id", "thread-1")
    checks.attr_eq(resume, "session.id", "thread-1")
    checks.require(
        json.loads(dict(resume.attributes)["sdk.hitl.resume_value"]) is True,
        "sdk.hitl.resume_value should be true",
    )
    return checks.failures


def run_hitl_stream() -> None:
    graph = _build_approval_graph()
    with ai_observability.workflow(**WORKFLOW):
        for _ in graph.stream(
            {"messages": []},
            config={"configurable": {"thread_id": WORKFLOW["workflow_id"]}},
        ):
            pass


def assert_hitl_stream(spans) -> list[str]:
    checks = ScenarioAssertions(spans)
    root = checks.require_single_root("approval")
    if root is None:
        return checks.failures
    checks.status_ok(root)
    checks.attr_eq(root, "sdk.hitl.interrupted", "true")
    checks.attr_eq(root, "sdk.hitl.thread_id", "thread-1")
    checks.attr_eq(root, "sdk.hitl.node", "human_review")
    payload = dict(root.attributes or {}).get("sdk.hitl.interrupt_payload")
    checks.require(
        isinstance(payload, str) and json.loads(payload) == [INTERRUPT_PAYLOAD],
        f"sdk.hitl.interrupt_payload mismatch: {payload!r}",
    )
    return checks.failures


SCENARIOS: list[Scenario] = [
    Scenario(
        id="lg_basic",
        framework="langgraph",
        description="linear graph: node CHAIN spans under the workflow root, langgraph_node metadata",
        run=run_basic,
        assert_trace=assert_basic,
    ),
    Scenario(
        id="lg_hitl_interrupt",
        framework="langgraph",
        description="interrupt() pauses for approval: root OK, sdk.hitl.* stamped, no error",
        run=run_hitl_interrupt,
        assert_trace=assert_hitl_interrupt,
    ),
    Scenario(
        id="lg_hitl_resume",
        framework="langgraph",
        description="Command(resume=True) continues the same thread AND the same trace: sdk.hitl.resume_value, one trace",
        run=run_hitl_resume,
        assert_trace=assert_hitl_resume,
    ),
    Scenario(
        id="lg_hitl_stream",
        framework="langgraph",
        description="streaming interrupt captured via the lifecycle hook",
        run=run_hitl_stream,
        assert_trace=assert_hitl_stream,
    ),
]