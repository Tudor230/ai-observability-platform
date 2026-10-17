"""Loop detection (ADR-0014): ingest re-derivation, flag persistence, API."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from helpers import build_request, build_span

from aiobs_backend.alerts import evaluate_alerts
from aiobs_backend.models import Execution, Span

KEY = "test-key"
SIG_A = "aaaabbbbccccdddd"
SIG_B = "1111222233334444"
SIG_C = "5555666677778888"


def _headers():
    return {"x-project-name": "proj-1", "authorization": f"Bearer {KEY}"}


def _now():
    return datetime.now(timezone.utc)


def _root(trace_id: int, start: datetime):
    return build_span(
        name="checkout",
        oi_kind="CHAIN",
        span_id=1,
        trace_id=trace_id,
        start=start,
        end=start + timedelta(seconds=5),
        attrs={"sdk.project_id": "proj-1", "sdk.workflow_id": f"wf-{trace_id}"},
    )


def _tool(trace_id: int, span_id: int, start: datetime, sig: str | None, name="lookup_order"):
    attrs = {"tool.name": name}
    if sig is not None:
        attrs["sdk.call.sig"] = sig
    return build_span(
        name=name,
        oi_kind="TOOL",
        span_id=span_id,
        trace_id=trace_id,
        parent_span_id=1,
        start=start,
        end=start + timedelta(milliseconds=100),
        attrs=attrs,
    )


def _llm(trace_id: int, span_id: int, start: datetime, sig: str | None, name="llm_call"):
    attrs = {"llm.model_name": "gpt-4o-mini", "llm.provider": "openai"}
    if sig is not None:
        attrs["sdk.call.sig"] = sig
    return build_span(
        name=name,
        oi_kind="LLM",
        span_id=span_id,
        trace_id=trace_id,
        parent_span_id=1,
        start=start,
        end=start + timedelta(milliseconds=200),
        attrs=attrs,
    )


def _post(client, spans):
    resp = client.post(
        "/api/v1/traces", content=build_request(spans), headers=_headers()
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _execution(session_factory, trace_id: int) -> Execution:
    with session_factory() as session:
        ex = (
            session.query(Execution)
            .filter(Execution.trace_id == f"{trace_id:032x}")
            .one()
        )
        session.expunge(ex)
        return ex


def test_repeated_tool_calls_flag_the_execution(client, session_factory, project):
    now = _now()
    spans = [_root(300, now)] + [
        _tool(300, 2 + i, now + timedelta(seconds=i), SIG_A) for i in range(3)
    ]
    _post(client, spans)

    ex = _execution(session_factory, 300)
    assert ex.loop_detected is True
    assert ex.status == "ok"
    assert ex.loop_info["signals"] == ["tool_repeat"]
    assert ex.loop_info["tool_repeats"] == 3
    assert ex.loop_info["llm_repeats"] == 0
    assert ex.loop_info["cycle_repeats"] == 0

    with session_factory() as session:
        row = (
            session.query(Span)
            .filter(Span.name == "lookup_order")
            .first()
        )
        assert row.call_sig == SIG_A


def test_below_threshold_is_clean(client, session_factory, project):
    now = _now()
    spans = [_root(301, now)] + [
        _tool(301, 2 + i, now + timedelta(seconds=i), SIG_A) for i in range(2)
    ]
    _post(client, spans)

    ex = _execution(session_factory, 301)
    assert ex.loop_detected is False
    assert ex.loop_info is None


def test_signature_equal_cycle_flags(client, session_factory, project):
    now = _now()
    spans = [_root(302, now)]
    for index in range(3):
        spans.append(_llm(302, 10 + index * 2, now + timedelta(seconds=index * 2), SIG_B))
        spans.append(_tool(302, 11 + index * 2, now + timedelta(seconds=index * 2 + 1), SIG_C))
    _post(client, spans)

    ex = _execution(session_factory, 302)
    assert ex.loop_detected is True
    info = ex.loop_info
    assert "cycle" in info["signals"]
    assert info["cycle_repeats"] == 3
    assert info["cycle_steps"] == ["llm_call", "lookup_order"]
    assert info["tool_repeats"] == 3 and info["llm_repeats"] == 3


def test_react_alternation_with_distinct_calls_stays_clean(client, session_factory, project):
    now = _now()
    spans = [_root(303, now)]
    for index in range(3):
        spans.append(
            _llm(303, 20 + index * 2, now + timedelta(seconds=index * 2), f"llm-{index}")
        )
        spans.append(
            _tool(303, 21 + index * 2, now + timedelta(seconds=index * 2 + 1), f"tool-{index}")
        )
    _post(client, spans)

    ex = _execution(session_factory, 303)
    assert ex.loop_detected is False


def test_late_batch_recomputes_the_flag(client, session_factory, project):
    now = _now()
    first = [_root(304, now)] + [
        _tool(304, 2 + i, now + timedelta(seconds=i), SIG_A) for i in range(2)
    ]
    _post(client, first)
    assert _execution(session_factory, 304).loop_detected is False

    _post(client, [_tool(304, 4, now + timedelta(seconds=2), SIG_A)])
    ex = _execution(session_factory, 304)
    assert ex.loop_detected is True
    assert ex.loop_info["tool_repeats"] == 3


def test_spans_without_signatures_are_ignored(client, session_factory, project):
    now = _now()
    spans = [_root(305, now)] + [
        _tool(305, 2 + i, now + timedelta(seconds=i), sig=None) for i in range(3)
    ]
    _post(client, spans)
    assert _execution(session_factory, 305).loop_detected is False


def test_executions_api_exposes_and_filters_the_flag(client, session_factory, project):
    now = _now()
    looped = [_root(306, now)] + [
        _tool(306, 2 + i, now + timedelta(seconds=i), SIG_A) for i in range(3)
    ]
    clean = [_root(307, now)] + [
        _tool(307, 2 + i, now + timedelta(seconds=i), f"sig-{i}") for i in range(3)
    ]
    _post(client, looped)
    _post(client, clean)

    all_body = client.get("/api/v1/executions?days=1").json()
    assert all_body["total"] == 2

    only_looped = client.get("/api/v1/executions?days=1&loop=true").json()
    assert only_looped["total"] == 1
    item = only_looped["items"][0]
    assert item["loop_detected"] is True
    assert item["loop_info"]["signals"] == ["tool_repeat"]

    only_clean = client.get("/api/v1/executions?days=1&loop=false").json()
    assert only_clean["total"] == 1
    assert only_clean["items"][0]["loop_detected"] is False

    detail = client.get(f"/api/v1/executions/{item['id']}").json()
    assert detail["loop_detected"] is True
    assert detail["loop_info"]["tool_repeats"] == 3


def test_loop_executions_rule_fires_warning(session_factory, project):
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        for index in range(5):
            session.add(
                Execution(
                    trace_id=f"loop-alert-{index:05d}",
                    project_id=project.id,
                    workflow_name="wf",
                    status="ok",
                    loop_detected=True,
                    started_at=now,
                    ended_at=now,
                )
            )
        session.commit()
        created = evaluate_alerts(session)
        session.commit()

    loop_alerts = [a for a in created if a["dimension_key"] == "loop_executions"]
    assert len(loop_alerts) == 1, created
    assert loop_alerts[0]["severity"] == "warning"
    assert "looped executions" in loop_alerts[0]["message"]

    with session_factory() as session:
        again = evaluate_alerts(session)
    assert not any(a["dimension_key"] == "loop_executions" for a in again)
