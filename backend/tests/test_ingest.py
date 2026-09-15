"""Integration tests: real OTLP ingest → pipeline → API read-back."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from helpers import build_request, build_span
from sqlalchemy import select

from aiobs_backend import analytics
from aiobs_backend.models import Alert, CostRecord, Execution, Span

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


def test_project_mismatch_skipped(client, session_factory, project):
    now = _now()
    root = build_span(
        name="checkout", oi_kind="CHAIN", span_id=1, trace_id=300,
        start=now, end=now + timedelta(seconds=1),
        attrs={"sdk.project_id": "other-proj", "sdk.client_id": "client-42"},
    )
    resp = client.post("/api/v1/traces", content=build_request([root]), headers=_headers())
    assert resp.status_code == 200
    assert resp.json()["traces"][0]["skipped"] == "project_mismatch"
    with session_factory() as session:
        assert session.execute(select(Execution)).first() is None


def test_project_scope_header(client, session_factory, project):
    client.post("/api/v1/traces", content=build_request(_happy_trace()), headers=_headers())
    with session_factory() as session:
        from helpers import seed_project

        seed_project(session, project_id="proj-2", api_key="k2", name="P2")
        session.commit()
    now = _now()
    root2 = build_span(
        name="other", oi_kind="CHAIN", span_id=1, trace_id=400,
        start=now, end=now + timedelta(seconds=1),
        attrs={"sdk.project_id": "proj-2", "sdk.client_id": "client-7"},
    )
    client.post(
        "/api/v1/traces",
        content=build_request([root2]),
        headers={"x-project-name": "proj-2", "authorization": "Bearer k2"},
    )
    scoped = client.get("/api/v1/executions", headers={"x-project-name": "proj-1"}).json()
    assert scoped["total"] == 1
    assert all(i["project_id"] == "proj-1" for i in scoped["items"])
    unscoped = client.get("/api/v1/executions").json()
    assert unscoped["total"] == 2


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


# ---------------------------------------------------------------------------
# Regression tests for the audit findings (docs/06-project-audit.md)
# ---------------------------------------------------------------------------


def _partial_children(trace_id: int = 100, prompt: int = 2000, completion: int = 1000):
    """A children-only batch: both spans point at parents outside the batch."""
    now = _now()
    llm = build_span(
        name="llm_call",
        oi_kind="LLM",
        span_id=2,
        trace_id=trace_id,
        parent_span_id=1,
        start=now + timedelta(milliseconds=100),
        end=now + timedelta(seconds=1),
        attrs={
            "llm.model_name": "gpt-4o-mini",
            "llm.provider": "openai",
            "llm.token_count.prompt": prompt,
            "llm.token_count.completion": completion,
            "llm.token_count.total": prompt + completion,
        },
    )
    tool = build_span(
        name="lookup_order",
        oi_kind="TOOL",
        span_id=3,
        trace_id=trace_id,
        parent_span_id=2,
        start=now + timedelta(seconds=1),
        end=now + timedelta(seconds=1.5),
        attrs={"tool.name": "lookup_order"},
    )
    return [llm, tool]


def test_costs_items_expose_total_cost(client, project):
    """F01: /costs must use the same `total_cost` key as every other aggregate."""
    client.post("/api/v1/traces", content=build_request(_happy_trace()), headers=_headers())
    for dimension in ("project", "client", "workflow", "model"):
        data = client.get(f"/api/v1/costs?dimension={dimension}").json()
        assert data["total"] >= 1, dimension
        for item in data["items"]:
            assert "total_cost" in item, (dimension, item)
            assert "cost" not in item, (dimension, item)


def test_costs_invalid_dimension_is_422(client, project):
    assert client.get("/api/v1/costs?dimension=bogus").status_code == 422


def test_partial_batch_merges_into_existing_execution(client, session_factory, project):
    """F02: a children-only re-send must merge, not create a bogus execution."""
    client.post("/api/v1/traces", content=build_request(_happy_trace()), headers=_headers())
    resp = client.post(
        "/api/v1/traces", content=build_request(_partial_children()), headers=_headers()
    )
    assert resp.status_code == 200, resp.text
    summary = resp.json()["traces"][0]
    assert summary.get("merged") == 2, summary

    with session_factory() as session:
        executions = session.execute(select(Execution)).scalars().all()
        assert len(executions) == 1
        ex = executions[0]
        assert ex.workflow_name == "checkout"  # identity preserved
        assert ex.total_tokens == 3000  # updated from the merged LLM span
        assert float(ex.total_cost) == pytest_approx(0.0009)
        assert len(session.execute(select(Span)).scalars().all()) == 3


def test_children_only_batch_without_execution_is_skipped(client, session_factory, project):
    """F02: no stored execution + no root in batch -> skip, never invent a root."""
    resp = client.post(
        "/api/v1/traces",
        content=build_request(_partial_children(trace_id=555)),
        headers=_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["traces"][0]["skipped"] == "root span not in batch"
    with session_factory() as session:
        assert session.execute(select(Execution)).first() is None
        assert session.execute(select(Span)).first() is None


def test_project_mismatch_preserves_existing_rows(client, session_factory, project):
    """F02: a rejected re-send must not delete the stored execution."""
    client.post("/api/v1/traces", content=build_request(_happy_trace()), headers=_headers())
    now = _now()
    bad_root = build_span(
        name="checkout",
        oi_kind="CHAIN",
        span_id=1,
        trace_id=100,
        start=now,
        end=now + timedelta(seconds=1),
        attrs={"sdk.project_id": "other-proj", "sdk.client_id": "client-42"},
    )
    resp = client.post(
        "/api/v1/traces", content=build_request([bad_root]), headers=_headers()
    )
    assert resp.json()["traces"][0]["skipped"] == "project_mismatch"
    with session_factory() as session:
        ex = session.execute(select(Execution)).scalar_one()
        assert ex.workflow_name == "checkout"
        assert len(session.execute(select(Span)).scalars().all()) == 3


def test_root_failure_kind_prefers_specific_descendant(client, session_factory, project):
    """F28: a generic failed wrapper must not mask the child's rate_limit."""
    now = _now()
    root = build_span(
        name="checkout", oi_kind="CHAIN", span_id=1, trace_id=600,
        start=now, end=now + timedelta(seconds=1),
        status=2,
        attrs={"sdk.project_id": "proj-1", "sdk.client_id": "client-42"},
    )
    llm = build_span(
        name="llm_call", oi_kind="LLM", span_id=2, trace_id=600, parent_span_id=1,
        start=now + timedelta(milliseconds=100), end=now + timedelta(seconds=1),
        status=2,
        status_message="OpenAI rate limit exceeded (429)",
        attrs={"llm.model_name": "gpt-4o-mini", "llm.provider": "openai"},
    )
    client.post("/api/v1/traces", content=build_request([root, llm]), headers=_headers())
    with session_factory() as session:
        ex = session.execute(select(Execution)).scalar_one()
        assert ex.status == "error"
        assert ex.root_error_kind == "rate_limit"


def test_unpriced_calls_surface_in_reads(client, session_factory, project):
    """F12: unpriced LLM calls are flagged, not silently reported as $0."""
    now = _now()
    root = build_span(
        name="checkout", oi_kind="CHAIN", span_id=1, trace_id=601,
        start=now, end=now + timedelta(seconds=1),
        attrs={"sdk.project_id": "proj-1", "sdk.client_id": "client-42"},
    )
    llm = build_span(
        name="llm_call", oi_kind="LLM", span_id=2, trace_id=601, parent_span_id=1,
        start=now + timedelta(milliseconds=100), end=now + timedelta(seconds=1),
        attrs={"llm.model_name": "mystery-model", "llm.provider": "unknown-vendor",
               "llm.token_count.prompt": 100, "llm.token_count.completion": 50},
    )
    resp = client.post("/api/v1/traces", content=build_request([root, llm]), headers=_headers())
    assert resp.json()["traces"][0]["unpriced_calls"] == 1

    item = client.get("/api/v1/executions").json()["items"][0]
    assert item["unpriced_calls"] == 1
    assert item["cost_complete"] is False
    assert item["total_cost"] is None


def test_alert_patch_requires_admin(client, session_factory, project):
    """F10: acknowledging an alert is a mutation and needs the admin key."""

    with session_factory() as session:
        alert = Alert(
            rule_id="test:alert-patch",
            severity="warning",
            message="test",
            dimension="budget",
        )
        session.add(alert)
        session.commit()
        alert_id = alert.id
    assert client.patch(f"/api/v1/alerts/{alert_id}?status=acknowledged").status_code == 401
    ok = client.patch(
        f"/api/v1/alerts/{alert_id}?status=acknowledged",
        headers={"x-admin-key": "admin"},
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "acknowledged"


def test_executions_days_filter(client, project):
    """F15: the dashboard's `days` filter must actually filter."""
    client.post("/api/v1/traces", content=build_request(_happy_trace()), headers=_headers())
    assert client.get("/api/v1/executions?days=1").json()["total"] == 1

    old = _now() - timedelta(days=10)
    tl = build_span(
        name="old_run", oi_kind="CHAIN", span_id=1, trace_id=700,
        start=old, end=old + timedelta(seconds=1),
        attrs={"sdk.project_id": "proj-1", "sdk.client_id": "client-42"},
    )
    client.post("/api/v1/traces", content=build_request([tl]), headers=_headers())
    assert client.get("/api/v1/executions?days=1").json()["total"] == 1
    assert client.get("/api/v1/executions?days=30").json()["total"] == 2


# ---------------------------------------------------------------------------
# Ingest hardening (F21)
# ---------------------------------------------------------------------------


def _single_root(trace_id: int, project_id: str = "proj-1"):
    now = _now()
    return [
        build_span(
            name="wf", oi_kind="CHAIN", span_id=1, trace_id=trace_id,
            start=now, end=now + timedelta(seconds=1),
            attrs={"sdk.project_id": project_id, "sdk.client_id": "client-42"},
        )
    ]


def test_malformed_otlp_body_is_400(client, project):
    resp = client.post("/api/v1/traces", content=b"definitely-not-protobuf", headers=_headers())
    assert resp.status_code == 400, resp.text
    assert "invalid OTLP payload" in resp.json()["detail"]


def test_oversized_body_is_rejected(client, project, monkeypatch):
    from aiobs_backend.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr(get_settings(), "max_ingest_bytes", 32)
    try:
        resp = client.post(
            "/api/v1/traces", content=build_request(_happy_trace()), headers=_headers()
        )
        assert resp.status_code == 413
    finally:
        get_settings.cache_clear()


def test_one_bad_trace_does_not_roll_back_the_batch(
    client, session_factory, project, monkeypatch
):
    from aiobs_backend.ingest import pipeline

    original = pipeline.process_trace

    def flaky(session, proj, raw_spans):
        if raw_spans[0].trace_id == "0000000000000000000000000000044d":  # 1101
            raise RuntimeError("boom")
        return original(session, proj, raw_spans)

    monkeypatch.setattr(pipeline, "process_trace", flaky)
    resp = client.post(
        "/api/v1/traces",
        content=build_request(_single_root(1100) + _single_root(1101)),
        headers=_headers(),
    )
    assert resp.status_code == 200, resp.text
    summaries = resp.json()["traces"]
    assert summaries[0]["status"] == "ok"
    assert summaries[1]["skipped"] == "processing_error"
    with session_factory() as session:
        assert len(session.execute(select(Execution)).scalars().all()) == 1


def test_estimated_token_flag_is_persisted(client, project):
    """F33: backfilled token counts carry sdk.tokens.estimated to the read API."""
    now = _now()
    root = build_span(
        name="checkout", oi_kind="CHAIN", span_id=1, trace_id=1700,
        start=now, end=now + timedelta(seconds=1),
        attrs={"sdk.project_id": "proj-1", "sdk.client_id": "client-42"},
    )
    llm = build_span(
        name="llm_call", oi_kind="LLM", span_id=2, trace_id=1700, parent_span_id=1,
        start=now + timedelta(milliseconds=10), end=now + timedelta(seconds=1),
        attrs={"llm.model_name": "gpt-4o-mini", "llm.provider": "openai",
               "llm.token_count.prompt": 7, "llm.token_count.completion": 3,
               "sdk.tokens.estimated": True},
    )
    client.post("/api/v1/traces", content=build_request([root, llm]), headers=_headers())
    execution_id = client.get("/api/v1/executions").json()["items"][0]["id"]
    spans = client.get(f"/api/v1/executions/{execution_id}/spans").json()["items"]
    llm_span = next(s for s in spans if s["kind"] == "LLM")
    assert llm_span["attributes"]["sdk.tokens.estimated"] is True



