"""Cost engine tests: provider-default fallback, unpriced -> NULL, cache/reasoning."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from helpers import build_request, build_span
from sqlalchemy import select

from aiobs_backend.models import Execution, Pricing, Span


def _headers():
    return {"x-project-name": "proj-1", "authorization": "Bearer test-key"}


def _now():
    return datetime.now(timezone.utc)


def _llm_trace(trace_id: int, attrs: dict, status_message: str | None = None, status: int = 1):
    now = _now()
    root = build_span(
        name="checkout", oi_kind="CHAIN", span_id=1, trace_id=trace_id,
        start=now, end=now + timedelta(seconds=1),
        attrs={"sdk.project_id": "proj-1", "sdk.client_id": "client-42"},
    )
    llm = build_span(
        name="llm", oi_kind="LLM", span_id=2, trace_id=trace_id, parent_span_id=1,
        start=now + timedelta(milliseconds=100), end=now + timedelta(seconds=1),
        status=status, status_message=status_message, attrs=attrs,
    )
    return [root, llm]


def test_unpriced_model_cost_is_null(client, session_factory, project):
    attrs = {
        "llm.model_name": "custom-model-xyz",
        "llm.provider": "openai",
        "llm.token_count.prompt": 100,
        "llm.token_count.completion": 50,
    }
    client.post("/api/v1/traces", content=build_request(_llm_trace(1, attrs)), headers=_headers())
    with session_factory() as session:
        ex = session.execute(select(Execution)).scalar_one()
        assert ex.total_cost is None  # unpriced -> NULL, not 0


def test_provider_default_fallback(client, session_factory, project):
    with session_factory() as session:
        session.add(
            Pricing(
                provider="acme",
                model="*",
                model_match="default",
                input_price_per_1m=1.0,
                output_price_per_1m=2.0,
                effective_from=datetime.now(timezone.utc),
            )
        )
        session.commit()
    attrs = {
        "llm.model_name": "acme-whatever",
        "llm.provider": "acme",
        "llm.token_count.prompt": 1000,
        "llm.token_count.completion": 500,
    }
    resp = client.post(
        "/api/v1/traces", content=build_request(_llm_trace(2, attrs)), headers=_headers()
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["traces"][0]["total_cost"] == pytest.approx(0.002)  # 1000*1 + 500*2 / 1e6


def test_cache_and_reasoning_tokens_costed(client, session_factory, project):
    # gpt-4o-mini: input 0.15, output 0.60, cache_read 0.075, cache_write 0.15, reasoning = output price.
    attrs = {
        "llm.model_name": "gpt-4o-mini",
        "llm.provider": "openai",
        "llm.token_count.prompt": 1000,
        "llm.token_count.completion": 500,
        "llm.token_count.total": 1500,
        "llm.token_count.prompt_details.cache_read": 400,
        "llm.token_count.prompt_details.cache_write": 200,
        "llm.token_count.completion_details.reasoning": 100,
    }
    client.post("/api/v1/traces", content=build_request(_llm_trace(3, attrs)), headers=_headers())
    with session_factory() as session:
        span = session.execute(select(Span).where(Span.kind == "LLM")).scalar_one()
        # (1000-400-200)*0.15 + 400*0.075 + 200*0.15 + (500-100)*0.60 + 100*0.60
        expected = (400 * 0.15 + 400 * 0.075 + 200 * 0.15 + 400 * 0.60 + 100 * 0.60) / 1_000_000
        assert float(span.cost) == pytest.approx(expected)
        ex = session.execute(select(Execution)).scalar_one()
        assert float(ex.total_cost) == pytest.approx(expected)