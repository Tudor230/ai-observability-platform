"""Pricing history (F30): resolved rates are snapshotted and deletion is guarded."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from helpers import build_request, build_span
from sqlalchemy import select

from aiobs_backend.models import CostRecord, Pricing

KEY = "test-key"
ADMIN = {"x-admin-key": "admin"}


def _headers() -> dict:
    return {"x-project-name": "proj-1", "authorization": f"Bearer {KEY}"}


def _priced_trace(trace_id: int):
    now = datetime.now(timezone.utc)
    root = build_span(
        name="checkout", oi_kind="CHAIN", span_id=1, trace_id=trace_id,
        start=now, end=now + timedelta(seconds=1),
        attrs={"sdk.project_id": "proj-1", "sdk.client_id": "client-42"},
    )
    llm = build_span(
        name="llm_call", oi_kind="LLM", span_id=2, trace_id=trace_id, parent_span_id=1,
        start=now + timedelta(milliseconds=10), end=now + timedelta(seconds=1),
        attrs={"llm.model_name": "gpt-4o-mini", "llm.provider": "openai",
               "llm.token_count.prompt": 1000, "llm.token_count.completion": 500},
    )
    return [root, llm]


def test_cost_records_snapshot_the_resolved_rates(client, session_factory, project):
    client.post("/api/v1/traces", content=build_request(_priced_trace(1600)), headers=_headers())
    with session_factory() as session:
        record = session.execute(select(CostRecord)).scalar_one()
        assert record.unit_prices is not None
        assert record.unit_prices["input"] == 0.15
        assert record.unit_prices["output"] == 0.60
        assert record.unit_prices["effective_from"]


def test_referenced_pricing_cannot_be_deleted(client, session_factory, project):
    client.post("/api/v1/traces", content=build_request(_priced_trace(1601)), headers=_headers())
    with session_factory() as session:
        pricing_id = session.execute(
            select(Pricing.id).where(Pricing.model == "gpt-4o-mini")
        ).scalar_one()
    resp = client.delete(f"/api/v1/pricing/{pricing_id}", headers=ADMIN)
    assert resp.status_code == 409
    assert "referenced" in resp.json()["detail"]


def test_unreferenced_pricing_can_be_deleted(client, session_factory, project):
    with session_factory() as session:
        row = Pricing(
            provider="acme",
            model="unused",
            model_match="exact",
            input_price_per_1m=1.0,
            output_price_per_1m=1.0,
        )
        session.add(row)
        session.commit()
        pricing_id = row.id
    assert client.delete(f"/api/v1/pricing/{pricing_id}", headers=ADMIN).status_code == 200
