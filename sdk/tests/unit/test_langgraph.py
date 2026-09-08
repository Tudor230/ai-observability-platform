"""LangGraph human-in-the-loop auto-interception tests.

Covers the interception helpers, the trace-keyed registry, the boundary patch
and lifecycle hook against a real LangGraph graph, control-flow exception
filtering, and the enrichment-layer HITL stamping (see ticket 03).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import TypedDict

import pytest
import wrapt
from opentelemetry.trace.status import StatusCode

import ai_observability
from ai_observability._attributes import (
    METADATA,
    SDK_HITL_CHECKPOINT_ID,
    SDK_HITL_INTERRUPT_PAYLOAD,
    SDK_HITL_INTERRUPTED,
    SDK_HITL_NODE,
    SDK_HITL_RESUME_VALUE,
    SDK_HITL_THREAD_ID,
)
from ai_observability._config import Config
from ai_observability._errors import is_failed
from ai_observability._langgraph import (
    _extract_thread_id,
    _interrupts_from_result,
    _interrupts_json,
    instrument_langgraph,
    uninstrument_langgraph,
)
from ai_observability._state import HITLRegistry, get_state

from .helpers import as_dict, enrich, exception_event, make_span

TRACE = 0x1234
CFG_OFF = Config(project_id="p1", capture_prompts=False)

INTERRUPT_PAYLOAD = {"question": "Approve refund?", "amount": 42}


def _finished(tail):
    ai_observability.flush(timeout_millis=10_000)
    return list(tail.get_finished_spans())


def _root(spans):
    return next(s for s in spans if s.parent is None or s.parent.is_remote)


def _build_approval_graph():
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import interrupt

    class _State(TypedDict):
        messages: list[str]

    def human_review(state):
        decision = interrupt(INTERRUPT_PAYLOAD)
        return {"messages": state["messages"] + [f"decided:{decision}"]}

    return (
        StateGraph(_State)
        .add_node("human_review", human_review)
        .add_edge(START, "human_review")
        .add_edge("human_review", END)
        .compile(checkpointer=InMemorySaver())
    )


# --- interception helpers -----------------------------------------------------


def test_interrupts_from_result_only_dicts():
    assert _interrupts_from_result({"messages": []}) is None
    assert _interrupts_from_result("not a dict") is None
    interrupts = (SimpleNamespace(value="v"),)
    assert _interrupts_from_result({"__interrupt__": interrupts}) is interrupts


def test_interrupts_json_extracts_values():
    interrupts = (
        SimpleNamespace(value=INTERRUPT_PAYLOAD),
        SimpleNamespace(value="plain"),
    )
    assert json.loads(_interrupts_json(interrupts)) == [INTERRUPT_PAYLOAD, "plain"]


def test_interrupts_json_falls_back_to_str():
    class Weird:
        def __repr__(self):
            return "weird"

    payload = json.loads(_interrupts_json([SimpleNamespace(value=Weird())]))
    assert isinstance(payload[0], str)


def test_extract_thread_id_forms():
    assert _extract_thread_id({"configurable": {"thread_id": "t1"}}) == "t1"
    assert _extract_thread_id({"configurable": {"thread_id": 42}}) == "42"
    assert _extract_thread_id({"configurable": {}}) is None
    assert _extract_thread_id({"configurable": None}) is None
    assert _extract_thread_id({}) is None
    assert _extract_thread_id(None) is None


# --- registry -----------------------------------------------------------------


def test_registry_record_and_take():
    registry = HITLRegistry()
    registry.record(1, a="1", b="2")
    assert registry.take(1) == {"a": "1", "b": "2"}
    assert registry.take(1) == {}


def test_registry_first_writer_wins():
    registry = HITLRegistry()
    registry.record(1, a="first")
    registry.record(1, a="second", b="x")
    assert registry.take(1) == {"a": "first", "b": "x"}


def test_registry_ignores_none():
    registry = HITLRegistry()
    registry.record(1, a="1", b=None)
    assert registry.take(1) == {"a": "1"}


def test_registry_record_without_attrs_is_noop():
    registry = HITLRegistry()
    registry.record(1)
    assert registry.take(1) == {}


def test_registry_bounded_evicts_oldest():
    registry = HITLRegistry(max_entries=2)
    registry.record(1, a="1")
    registry.record(2, a="2")
    registry.record(3, a="3")
    assert registry.take(1) == {}
    assert registry.take(2) == {"a": "2"}
    assert registry.take(3) == {"a": "3"}


# --- control-flow exception filtering -----------------------------------------


@pytest.mark.parametrize(
    "exc_type",
    ["GraphInterrupt", "GraphBubbleUp", "Command", "ParentCommand",
     "langgraph.errors.GraphInterrupt"],
)
def test_control_flow_exception_events_not_failed(exc_type):
    ok = make_span(1, TRACE, None, events=[exception_event(exc_type, "paused")])
    assert not is_failed(ok)
    error = make_span(2, TRACE, None, status_code=StatusCode.ERROR,
                      events=[exception_event(exc_type, "paused")])
    assert not is_failed(error)


def test_error_status_without_event_is_failed():
    span = make_span(1, TRACE, None, status_code=StatusCode.ERROR)
    assert is_failed(span)


def test_real_exception_event_is_failed():
    ok = make_span(1, TRACE, None, events=[exception_event("ValueError", "boom")])
    assert is_failed(ok)
    error = make_span(2, TRACE, None, status_code=StatusCode.ERROR,
                      events=[exception_event("ValueError", "boom")])
    assert is_failed(error)


def test_mixed_control_flow_and_real_event_is_failed():
    span = make_span(
        1, TRACE, None, status_code=StatusCode.ERROR,
        events=[
            exception_event("GraphInterrupt", "paused"),
            exception_event("ValueError", "boom"),
        ],
    )
    assert is_failed(span)


# --- enrichment: HITL stamping -------------------------------------------------


def test_enrich_stamps_hitl_and_derives_node():
    get_state().hitl.record(
        TRACE,
        **{
            SDK_HITL_INTERRUPTED: "true",
            SDK_HITL_INTERRUPT_PAYLOAD: json.dumps([INTERRUPT_PAYLOAD]),
            SDK_HITL_THREAD_ID: "thread-1",
        },
    )
    node = make_span(
        1, TRACE, 99, name="human_review", kind="CHAIN",
        attributes={METADATA: json.dumps({"langgraph_node": "human_review"})},
        start_time=2_000_000_000,
    )
    root = make_span(2, TRACE, None, name="wf", kind="CHAIN")
    out = as_dict(enrich([root, node], CFG_OFF))
    assert out[2][SDK_HITL_INTERRUPTED] == "true"
    assert out[2][SDK_HITL_INTERRUPT_PAYLOAD] == json.dumps([INTERRUPT_PAYLOAD])
    assert out[2][SDK_HITL_THREAD_ID] == "thread-1"
    assert out[2][SDK_HITL_NODE] == "human_review"


def test_enrich_does_not_overwrite_existing_root_hitl():
    get_state().hitl.record(TRACE, **{SDK_HITL_INTERRUPT_PAYLOAD: "from-registry"})
    root = make_span(
        2, TRACE, None, name="wf", kind="CHAIN",
        attributes={SDK_HITL_INTERRUPT_PAYLOAD: "already-on-root"},
    )
    out = as_dict(enrich([root], CFG_OFF))
    assert out[2][SDK_HITL_INTERRUPT_PAYLOAD] == "already-on-root"


def test_enrich_no_hitl_when_nothing_recorded():
    root = make_span(2, TRACE, None, name="wf", kind="CHAIN")
    out = as_dict(enrich([root], CFG_OFF))
    assert SDK_HITL_INTERRUPTED not in out[2]
    assert SDK_HITL_NODE not in out[2]


def test_enrich_interrupt_is_not_an_error():
    get_state().hitl.record(TRACE, **{SDK_HITL_INTERRUPTED: "true"})
    node = make_span(
        1, TRACE, 99, name="human_review", kind="CHAIN",
        status_code=StatusCode.OK,
        events=[exception_event("langgraph.errors.GraphInterrupt", "paused")],
        attributes={METADATA: json.dumps({"langgraph_node": "human_review"})},
    )
    root = make_span(2, TRACE, None, name="wf", kind="CHAIN")
    out = enrich([root, node], CFG_OFF)
    root_out = next(s for s in out if s.name == "wf")
    assert root_out.status.status_code == StatusCode.OK
    assert "sdk.error.kind" not in dict(root_out.attributes)
    assert dict(root_out.attributes)[SDK_HITL_NODE] == "human_review"


# --- boundary patch + lifecycle hook (real LangGraph) --------------------------


def test_invoke_interrupt_records_hitl(tail_exporter):
    graph = _build_approval_graph()
    with ai_observability.workflow(name="approval", workflow_id="thread-1"):
        result = graph.invoke(
            {"messages": []},
            config={"configurable": {"thread_id": "thread-1"}},
        )
    assert "__interrupt__" in result
    spans = _finished(tail_exporter)
    root = _root(spans)
    attrs = dict(root.attributes)
    assert root.status.status_code == StatusCode.OK
    assert attrs[SDK_HITL_INTERRUPTED] == "true"
    assert json.loads(attrs[SDK_HITL_INTERRUPT_PAYLOAD]) == [INTERRUPT_PAYLOAD]
    assert attrs[SDK_HITL_THREAD_ID] == "thread-1"
    assert attrs[SDK_HITL_NODE] == "human_review"
    assert "sdk.error.kind" not in attrs


def test_invoke_resume_records_resume_value(tail_exporter):
    from langgraph.types import Command

    graph = _build_approval_graph()
    config = {"configurable": {"thread_id": "thread-1"}}
    with ai_observability.workflow(name="approval", workflow_id="thread-1"):
        graph.invoke({"messages": []}, config=config)
    ai_observability.flush(timeout_millis=10_000)
    tail_exporter.clear()

    with ai_observability.workflow(name="approval", workflow_id="thread-1"):
        graph.invoke(Command(resume=True), config=config)
    spans = _finished(tail_exporter)
    root = _root(spans)
    attrs = dict(root.attributes)
    assert root.status.status_code == StatusCode.OK
    assert attrs[SDK_HITL_INTERRUPTED] == "false"
    assert json.loads(attrs[SDK_HITL_RESUME_VALUE]) is True
    assert attrs[SDK_HITL_THREAD_ID] == "thread-1"
    assert SDK_HITL_CHECKPOINT_ID in attrs


def test_stream_interrupt_records_hitl(tail_exporter):
    graph = _build_approval_graph()
    with ai_observability.workflow(name="approval", workflow_id="thread-2"):
        for _ in graph.stream(
            {"messages": []},
            config={"configurable": {"thread_id": "thread-2"}},
        ):
            pass
    spans = _finished(tail_exporter)
    root = _root(spans)
    attrs = dict(root.attributes)
    assert attrs[SDK_HITL_INTERRUPTED] == "true"
    assert json.loads(attrs[SDK_HITL_INTERRUPT_PAYLOAD]) == [INTERRUPT_PAYLOAD]
    assert attrs[SDK_HITL_THREAD_ID] == "thread-2"
    assert attrs[SDK_HITL_NODE] == "human_review"


@pytest.mark.asyncio
async def test_ainvoke_interrupt_records_hitl(tail_exporter):
    graph = _build_approval_graph()
    with ai_observability.workflow(name="approval", workflow_id="thread-1"):
        result = await graph.ainvoke(
            {"messages": []},
            config={"configurable": {"thread_id": "thread-1"}},
        )
    assert "__interrupt__" in result
    spans = _finished(tail_exporter)
    root = _root(spans)
    attrs = dict(root.attributes)
    assert attrs[SDK_HITL_INTERRUPTED] == "true"
    assert json.loads(attrs[SDK_HITL_INTERRUPT_PAYLOAD]) == [INTERRUPT_PAYLOAD]


@pytest.mark.asyncio
async def test_astream_interrupt_records_hitl(tail_exporter):
    graph = _build_approval_graph()
    with ai_observability.workflow(name="approval", workflow_id="thread-2"):
        async for _ in graph.astream(
            {"messages": []},
            config={"configurable": {"thread_id": "thread-2"}},
        ):
            pass
    spans = _finished(tail_exporter)
    root = _root(spans)
    assert dict(root.attributes)[SDK_HITL_INTERRUPTED] == "true"


def test_plain_graph_has_no_hitl_noise(tail_exporter):
    from langgraph.graph import END, START, StateGraph

    class _State(TypedDict):
        messages: list[str]

    def node_a(state):
        return {"messages": state["messages"] + ["a"]}

    graph = (
        StateGraph(_State)
        .add_node("node_a", node_a)
        .add_edge(START, "node_a")
        .add_edge("node_a", END)
        .compile()
    )
    with ai_observability.workflow(name="plain", workflow_id="w-1"):
        graph.invoke({"messages": []})
    spans = _finished(tail_exporter)
    root = _root(spans)
    attrs = dict(root.attributes)
    assert SDK_HITL_INTERRUPTED not in attrs
    assert SDK_HITL_THREAD_ID not in attrs
    assert root.status.status_code == StatusCode.OK


def test_boundary_patch_pass_through(tail_exporter):
    graph = _build_approval_graph()
    config = {"configurable": {"thread_id": "thread-1"}}
    with ai_observability.workflow(name="approval", workflow_id="thread-1"):
        result = graph.invoke({"messages": []}, config=config)
    # Interrupt payload intact and invoke returned normally (no exception).
    assert result["__interrupt__"][0].value == INTERRUPT_PAYLOAD


def test_boundary_patch_rethrows_real_errors(tail_exporter):
    from langgraph.graph import END, START, StateGraph

    class _State(TypedDict):
        messages: list[str]

    def boom(state):
        raise RuntimeError("node exploded")

    graph = (
        StateGraph(_State)
        .add_node("boom", boom)
        .add_edge(START, "boom")
        .add_edge("boom", END)
        .compile()
    )
    with ai_observability.workflow(name="failing"):
        with pytest.raises(RuntimeError, match="node exploded"):
            graph.invoke({"messages": []})


# --- instrumentation lifecycle -------------------------------------------------


def test_instrument_idempotent_and_uninstrument_restores():
    from langgraph.pregel import Pregel

    original = Pregel.__dict__.get("invoke")
    try:
        instrument_langgraph()
        instrument_langgraph()  # must be idempotent (no double wrap)
        assert isinstance(Pregel.__dict__["invoke"], wrapt.FunctionWrapper)
        assert Pregel.__dict__["invoke"] is not original
    finally:
        uninstrument_langgraph()
    assert Pregel.__dict__["invoke"] is original


def test_lifecycle_hook_injected():
    from langgraph.pregel import main as lg_pregel_main

    try:
        instrument_langgraph()
        fn = getattr(lg_pregel_main, "get_sync_graph_callback_manager_for_config")
        assert isinstance(fn, wrapt.FunctionWrapper)
        manager = fn({"configurable": {"thread_id": "t1"}}, run_id=None)
        assert any(type(h).__name__ == "_HITLLifecycleHandler" for h in manager.handlers)
    finally:
        uninstrument_langgraph()


def test_lifecycle_handler_records_interrupt(tail_exporter):
    from langgraph.callbacks import GraphCallbackHandler, GraphInterruptEvent
    from langgraph.types import Interrupt

    from ai_observability._langgraph import _make_lifecycle_handler

    tracer = get_state().get_tracer()
    handler = _make_lifecycle_handler(GraphCallbackHandler)()
    event = GraphInterruptEvent(
        run_id=None,
        status="pending",
        checkpoint_id="ckpt-1",
        checkpoint_ns=(),
        interrupts=(Interrupt(value=INTERRUPT_PAYLOAD, id="i1"),),
    )
    with tracer.start_as_current_span("root") as span:
        handler.on_interrupt(event)
    pending = get_state().hitl.take(span.context.trace_id)
    assert pending[SDK_HITL_INTERRUPTED] == "true"
    assert json.loads(pending[SDK_HITL_INTERRUPT_PAYLOAD]) == [INTERRUPT_PAYLOAD]