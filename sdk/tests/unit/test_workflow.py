"""Workflow + span manual API: attributes, hierarchy, nesting, decorators."""

from __future__ import annotations

import json

import pytest

import ai_observability
from ai_observability._attributes import (
    INPUT_VALUE,
    METADATA,
    OPENINFERENCE_SPAN_KIND,
    OUTPUT_VALUE,
    SDK_CLIENT_ID,
    SDK_CAPTURE_PROMPTS,
    SDK_ERROR_MESSAGE,
    SDK_ERROR_TYPE,
    SDK_PROJECT_ID,
    SDK_WORKFLOW_ID,
    SDK_WORKFLOW_VERSION,
    SESSION_ID,
)
from opentelemetry.trace.status import StatusCode


def _finished(tail):
    ai_observability.flush()
    return list(tail.get_finished_spans())


def test_workflow_context_manager_attributes(tail_exporter):
    with ai_observability.workflow(
        name="checkout",
        client_id="client-42",
        workflow_id="order-123",
        version="v2",
        context={"channel": "web"},
        user_id="user-7",
    ):
        pass
    spans = _finished(tail_exporter)
    assert len(spans) == 1
    root = spans[0]
    attrs = dict(root.attributes)
    assert root.name == "checkout"
    assert attrs[OPENINFERENCE_SPAN_KIND] == "CHAIN"
    assert attrs[SDK_CLIENT_ID] == "client-42"
    assert attrs[SDK_PROJECT_ID] == "proj-1"
    assert attrs[SDK_WORKFLOW_ID] == "order-123"
    assert attrs[SESSION_ID] == "order-123"
    assert attrs[SDK_WORKFLOW_VERSION] == "v2"
    assert attrs["user.id"] == "user-7"
    assert json.loads(attrs[METADATA]) == {"channel": "web"}
    assert root.status.status_code == StatusCode.OK


def test_workflow_decorator_sync(tail_exporter):
    @ai_observability.workflow(name="decorated", client_id="c1", workflow_id="w1")
    def run():
        return 42

    assert run() == 42
    spans = _finished(tail_exporter)
    assert len(spans) == 1
    assert spans[0].name == "decorated"
    assert dict(spans[0].attributes)[SESSION_ID] == "w1"


@pytest.mark.asyncio
async def test_workflow_decorator_async(tail_exporter):
    @ai_observability.workflow(name="async-decorated", client_id="c1", workflow_id="w2")
    async def run():
        return "ok"

    assert await run() == "ok"
    spans = _finished(tail_exporter)
    assert len(spans) == 1
    assert spans[0].name == "async-decorated"


def test_workflow_decorator_full_parameters(tail_exporter):
    """The @workflow decorator honors the same parameters as with workflow(...)."""
    @ai_observability.workflow(
        name="decorated",
        client_id="c1",
        workflow_id="w9",
        version="v2",
        context={"channel": "web"},
        user_id="user-7",
        capture_prompts=True,
    )
    def run():
        return 42

    assert run() == 42
    spans = _finished(tail_exporter)
    assert len(spans) == 1
    attrs = dict(spans[0].attributes)
    assert attrs[SDK_CLIENT_ID] == "c1"
    assert attrs[SDK_PROJECT_ID] == "proj-1"
    assert attrs[SDK_WORKFLOW_ID] == "w9"
    assert attrs[SESSION_ID] == "w9"
    assert attrs[SDK_WORKFLOW_VERSION] == "v2"
    assert attrs["user.id"] == "user-7"
    assert json.loads(attrs[METADATA]) == {"channel": "web"}
    assert attrs[SDK_CAPTURE_PROMPTS] == "true"


def test_workflow_nesting(tail_exporter):
    with ai_observability.workflow(name="outer", workflow_id="o-1"):
        with ai_observability.workflow(name="inner", workflow_id="i-1"):
            pass
    spans = _finished(tail_exporter)
    assert len(spans) == 2
    outer = next(s for s in spans if s.name == "outer")
    inner = next(s for s in spans if s.name == "inner")
    assert inner.parent.span_id == outer.context.span_id
    assert dict(outer.attributes)[SESSION_ID] == "o-1"
    assert dict(inner.attributes)[SESSION_ID] == "i-1"


def test_workflow_deterministic_trace_continuation(tail_exporter):
    """Two root workflows sharing a workflow_id join ONE trace (Langfuse-style
    deterministic trace-id continuation), even across separate executions."""
    from ai_observability._ids import trace_id_from_seed

    with ai_observability.workflow(name="wf", workflow_id="thread-1"):
        pass
    first = _finished(tail_exporter)[0]
    tail_exporter.clear()

    with ai_observability.workflow(name="wf", workflow_id="thread-1"):
        pass
    second = _finished(tail_exporter)[0]

    assert first.context.trace_id == trace_id_from_seed("thread-1")
    assert second.context.trace_id == trace_id_from_seed("thread-1")
    assert first.context.trace_id == second.context.trace_id
    assert first.context.span_id != second.context.span_id


def test_workflow_distinct_ids_distinct_traces(tail_exporter):
    with ai_observability.workflow(name="wf", workflow_id="a"):
        pass
    with ai_observability.workflow(name="wf", workflow_id="b"):
        pass
    spans = _finished(tail_exporter)
    assert len({s.context.trace_id for s in spans}) == 2


def test_workflow_without_id_stays_random(tail_exporter):
    with ai_observability.workflow(name="wf"):
        pass
    with ai_observability.workflow(name="wf"):
        pass
    spans = _finished(tail_exporter)
    assert len({s.context.trace_id for s in spans}) == 2


def test_capture_prompts_override_stamp(tail_exporter):
    with ai_observability.workflow(name="w", capture_prompts=True):
        pass
    with ai_observability.workflow(name="w2", capture_prompts=False):
        pass
    spans = _finished(tail_exporter)
    stamped = {s.name: dict(s.attributes).get(SDK_CAPTURE_PROMPTS) for s in spans}
    assert stamped == {"w": "true", "w2": "false"}


def test_workflow_records_body_exception(tail_exporter):
    with pytest.raises(ValueError):
        with ai_observability.workflow(name="failing"):
            raise ValueError("boom")
    spans = _finished(tail_exporter)
    assert len(spans) == 1
    root = spans[0]
    assert root.status.status_code == StatusCode.ERROR
    events = [e for e in root.events if e.name == "exception"]
    assert len(events) == 1
    assert dict(events[0].attributes)["exception.type"] == "ValueError"


def test_span_helper_under_workflow(tail_exporter):
    with ai_observability.workflow(name="wf", workflow_id="w-1"):
        with ai_observability.span("validate_output", context={"checks": 3}):
            pass
    spans = _finished(tail_exporter)
    assert len(spans) == 2
    step = next(s for s in spans if s.name == "validate_output")
    root = next(s for s in spans if s.name == "wf")
    assert step.parent.span_id == root.context.span_id
    assert dict(step.attributes)[OPENINFERENCE_SPAN_KIND] == "CHAIN"
    assert json.loads(dict(step.attributes)[METADATA]) == {"checks": 3}


def test_span_helper_records_exception(tail_exporter):
    with pytest.raises(RuntimeError):
        with ai_observability.span("step"):
            raise RuntimeError("nope")
    spans = _finished(tail_exporter)
    step = spans[0]
    assert step.status.status_code == StatusCode.ERROR


def test_span_decorator_parameters_match_context_manager(tail_exporter):
    """@span(name=..., context=...) behaves like with span(...), plus it
    captures input.value/output.value (visible with capture_prompts on)."""
    @ai_observability.span(name="check", context={"checks": 3})
    def validate(answer):
        return answer

    with ai_observability.workflow(name="wf", workflow_id="w-1", capture_prompts=True):
        result = validate("ok")

    assert result == "ok"
    spans = _finished(tail_exporter)
    check = next(s for s in spans if s.name == "check")
    root = next(s for s in spans if s.name == "wf")
    attrs = dict(check.attributes)
    assert check.parent.span_id == root.context.span_id
    assert attrs[OPENINFERENCE_SPAN_KIND] == "CHAIN"
    assert json.loads(attrs[METADATA]) == {"checks": 3}
    assert json.loads(attrs[INPUT_VALUE]) == {"answer": "ok"}
    assert json.loads(attrs[OUTPUT_VALUE]) == "ok"
    assert check.status.status_code == StatusCode.OK


def test_span_decorator_captures_input_even_on_error(tail_exporter):
    """A failing decorated function keeps its captured input, records the
    exception as a span error, and propagates the failure to the workflow root."""
    @ai_observability.span(name="check")
    def validate(answer):
        raise RuntimeError("nope")

    with ai_observability.workflow(name="wf", workflow_id="w-1", capture_prompts=True):
        with pytest.raises(RuntimeError):
            validate("bad")

    spans = _finished(tail_exporter)
    check = next(s for s in spans if s.name == "check")
    root = next(s for s in spans if s.name == "wf")
    attrs = dict(check.attributes)
    assert check.status.status_code == StatusCode.ERROR
    assert any(e.name == "exception" for e in check.events)
    assert json.loads(attrs[INPUT_VALUE]) == {"answer": "bad"}
    assert attrs[SDK_ERROR_TYPE] == "RuntimeError"
    assert "nope" in attrs[SDK_ERROR_MESSAGE]
    assert root.status.status_code == StatusCode.ERROR


@pytest.mark.asyncio
async def test_span_decorator_async(tail_exporter):
    @ai_observability.span(name="acheck")
    async def validate(answer):
        return f"v:{answer}"

    with ai_observability.workflow(name="wf", workflow_id="w-1", capture_prompts=True):
        result = await validate("ok")

    assert result == "v:ok"
    spans = _finished(tail_exporter)
    check = next(s for s in spans if s.name == "acheck")
    attrs = dict(check.attributes)
    assert attrs[OPENINFERENCE_SPAN_KIND] == "CHAIN"
    assert json.loads(attrs[INPUT_VALUE]) == {"answer": "ok"}
    assert json.loads(attrs[OUTPUT_VALUE]) == "v:ok"


def test_uninitialized_sdk_is_noop():
    # No init() call: workflow/span must not raise.
    with ai_observability.workflow(name="noop"):
        with ai_observability.span("step"):
            pass
    ai_observability.flush()
    ai_observability.shutdown()