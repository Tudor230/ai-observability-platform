"""Workflow + span manual API: attributes, hierarchy, nesting, decorators."""

from __future__ import annotations

import json

import pytest

import ai_observability
from ai_observability._attributes import (
    METADATA,
    OPENINFERENCE_SPAN_KIND,
    SDK_CLIENT_ID,
    SDK_CAPTURE_PROMPTS,
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


def test_uninitialized_sdk_is_noop():
    # No init() call: workflow/span must not raise.
    with ai_observability.workflow(name="noop"):
        with ai_observability.span("step"):
            pass
    ai_observability.flush()
    ai_observability.shutdown()