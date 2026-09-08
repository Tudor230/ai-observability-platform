"""Integration tests: real OTLP ingest → pipeline → API read-back."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from aiobs_backend import analytics
from aiobs_backend.models import Alert, Budget, CostRecord, Execution, Span

from helpers import build_request, build_span

KEY = "test-key"


def _headers():
    return {"x-project-name": "proj-1", "authorization": f"Bearer {KEY}"}


def _now():
    return datetime.now(timezone.utc)


def _happy_trace():
    now = _now()
    root = build_span(
        name="checkout",
        oi_kind="CHAIN",
        span_id=1,
        trace_id=100,
        start=now,
        end=now + timedelta(seconds=2),
        attrs={
            "sdk.project_id": "proj-1",
            "sdk.client_id": "client-42",
            "sdk.workflow_id": "order-123",
            "sdk.workflow.version": "v2",
            "session.id": "order-123",
            "metadata": '{"channel": "web"}',
        },
    )
    llm = build_span(
        name="llm_call",
        oi_kind="LLM",
        span_id=2,
        trace_id=100,
        parent_span_id=1,
        start=now + timedelta(milliseconds=100),
        end=now + timedelta(seconds=1),
        attrs={
            "llm.model_name": "gpt-4o-mini",
            "llm.provider": "openai",
            "llm.token_count.prompt": 1000,
            "llm.token_count.completion": 500,
            "llm.token_count.total": 1500,
        },
    )
    tool = build_span(
        name="lookup_order",
        oi_kind="TOOL",
        span_id=3,
        trace_id=100,
        parent_span_id=2,
        start=now + timedelta(seconds=1),
        end=now + timedelta(seconds=1.5),
        attrs={"tool.name": "lookup_order"},
    )
    return [root, llm, tool]


def test_happy_path_ingest_and_cost(client, session_factory, project):
    resp = client.post("/api/v1/traces", content=build_request(_happy_trace()), headers=_headers())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ingested"] == 1
    summary = body["traces"][0]
    assert summary["status"] == "ok"
    assert summary["total_cost"] == pytest_approx(0.00045)
    assert summary["total_tokens"] == 1500

    with session_factory() as session:
        ex = session.execute(select(Execution)).scalar_one()
        assert ex.workflow_name == "checkout"
        assert ex.workflow_id == "order-123"
        assert ex.client_id is not None
        assert ex.status == "ok"
        assert ex.llm_calls == 1
        assert ex.tool_calls == 1
        assert ex.input_tokens == 1000
        assert ex.output_tokens == 500
        assert float(ex.total_cost) == pytest_approx(0.00045)
        cost = session.execute(select(CostRecord)).scalar_one()
        assert float(cost.amount) == pytest_approx(0.00045)
        spans = session.execute(select(Span)).scalars().all()
        assert len(spans) == 3


def pytest_approx(value, rel=1e-9):
    import pytest

    return pytest.approx(value, rel=rel)


def test_failure_classification_rate_limit(client, session_factory, project):
    now = _now()
    root = build_span(
        name="checkout", oi_kind="CHAIN", span_id=1, trace_id=200,
        start=now, end=now + timedelta(seconds=1),
        attrs={"sdk.project_id": "proj-1", "sdk.client_id": "client-42"},
    )
    llm = build_span(
        name="llm_call", oi_kind="LLM", span_id=2, trace_id=200, parent_span_id=1,
        start=now + timedelta(milliseconds=100), end=now + timedelta(seconds=1),
        status=2,  # STATUS_CODE_ERROR
        status_message="API rate limit exceeded (429)",
        attrs={"llm.model_name": "gpt-4o-mini", "llm.provider": "openai",
               "llm.token_count.prompt": 100, "llm.token_count.completion": 10},
    )
    client.post("/api/v1/traces", content=build_request([root, llm]), headers=_headers())
    with session_factory() as session:
        ex = session.execute(select(Execution)).scalar_one()
        assert ex.status == "error"
        assert ex.root_error_kind == "rate_limit"
        span = session.execute(select(Span).where(Span.kind == "LLM")).scalar_one()
        assert span.error_kind == "rate_limit"


def test_auth_rejected(client, project):
    bad = {"x-project-name": "proj-1", "authorization": "Bearer wrong"}
    resp = client.post("/api/v1/traces", content=build_request(_happy_trace()), headers=bad)
    assert resp.status_code == 401


def test_api_reads(client, session_factory, project):
    client.post("/api/v1/traces", content=build_request(_happy_trace()), headers=_headers())
    # overview
    ov = client.get("/api/v1/overview").json()
    assert ov["executions"] == 1
    assert ov["total_cost"] > 0
    # executions list
    lst = client.get("/api/v1/executions").json()
    assert lst["total"] == 1
    ex_id = lst["items"][0]["id"]
    # detail
    det = client.get(f"/api/v1/executions/{ex_id}").json()
    assert det["workflow"] == "checkout"
    assert det["client_id"] == "client-42"
    # spans
    spans = client.get(f"/api/v1/executions/{ex_id}/spans").json()
    assert spans["total"] == 3
    # failures (empty for ok)
    fails = client.get(f"/api/v1/executions/{ex_id}/failures").json()
    assert fails["error_count"] == 0
    # workflows / clients / costs
    assert client.get("/api/v1/workflows").json()["total"] == 1
    assert client.get("/api/v1/clients").json()["total"] == 1
    costs = client.get("/api/v1/costs?dimension=project").json()
    assert costs["total"] == 1


def test_metrics_rollup(client, session_factory, project):
    client.post("/api/v1/traces", content=build_request(_happy_trace()), headers=_headers())
    with session_factory() as session:
        analytics.rollup_recent(session)
        session.commit()
    metrics = client.get("/api/v1/metrics?dimension=total").json()
    assert metrics["total"] >= 1
    m = metrics["items"][0]
    assert m["executions"] == 1
    assert m["total_cost"] > 0


def test_budget_alert(client, session_factory, project):
    client.post("/api/v1/traces", content=build_request(_happy_trace()), headers=_headers())
    admin = {"x-admin-key": "admin"}
    with session_factory() as session:
        from helpers import seed_project

        seed_project(session, project_id="proj-2", api_key="k2", name="P2")
        session.commit()
    # create a tiny budget to force an alert
    budget = client.post(
        "/api/v1/budgets",
        json={"name": "tiny", "amount": 0.00001, "period": "2000-01-01"},
        headers=admin,
    )
    assert budget.status_code == 200, budget.text
    with session_factory() as session:
        from aiobs_backend import alerts

        created = alerts.evaluate_alerts(session)
        session.commit()
    assert created, "expected at least one alert"
    alerts_list = client.get("/api/v1/alerts?status=open").json()
    assert alerts_list["total"] >= 1
    assert alerts_list["items"][0]["severity"] == "critical"

