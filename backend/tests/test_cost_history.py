"""Pricing history (F08): effective_from gates which price a trace uses."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from helpers import build_request, build_span

from aiobs_backend.models import Pricing

KEY = "test-key"


def _headers():
    return {"x-project-name": "proj-1", "authorization": f"Bearer {KEY}"}


def _trace(trace_id: int, start: datetime, prompt: int = 1000, completion: int = 1000):
    root = build_span(
        name="checkout", oi_kind="CHAIN", span_id=1, trace_id=trace_id,
        start=start, end=start + timedelta(seconds=1),
        attrs={"sdk.project_id": "proj-1", "sdk.client_id": "client-42"},
    )
    llm = build_span(
        name="llm_call", oi_kind="LLM", span_id=2, trace_id=trace_id, parent_span_id=1,
        start=start + timedelta(milliseconds=100), end=start + timedelta(seconds=1),
        attrs={"llm.model_name": "m1", "llm.provider": "acme",
               "llm.token_count.prompt": prompt, "llm.token_count.completion": completion},
    )
    return [root, llm]


def _add_price(session, *, amount_in: float, amount_out: float, effective_from: datetime):
    session.add(
        Pricing(
            provider="acme",
            model="m1",
            model_match="exact",
            input_price_per_1m=amount_in,
            output_price_per_1m=amount_out,
            effective_from=effective_from,
        )
    )
    session.commit()


def test_future_price_is_not_applied_to_earlier_executions(client, session_factory, project):
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        _add_price(session, amount_in=0.10, amount_out=0.20, effective_from=now - timedelta(days=1))
        # A price effective tomorrow must not apply to a trace that ran today.
        _add_price(session, amount_in=9.99, amount_out=9.99, effective_from=now + timedelta(days=1))

    resp = client.post("/api/v1/traces", content=build_request(_trace(901, now)), headers=_headers())
    assert resp.status_code == 200, resp.text
    # 1000 * 0.10/1M + 1000 * 0.20/1M = 0.0003
    assert abs(resp.json()["traces"][0]["total_cost"] - 0.0003) < 1e-12


def test_new_price_applies_to_later_executions(client, session_factory, project):
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        _add_price(session, amount_in=0.10, amount_out=0.20, effective_from=now - timedelta(hours=2))
    first = client.post("/api/v1/traces", content=build_request(_trace(902, now)), headers=_headers())
    assert abs(first.json()["traces"][0]["total_cost"] - 0.0003) < 1e-12

    with session_factory() as session:
        _add_price(session, amount_in=0.30, amount_out=0.60, effective_from=now - timedelta(hours=1))
    second = client.post("/api/v1/traces", content=build_request(_trace(903, now)), headers=_headers())
    # The newest price effective before the trace start wins: 0.0009.
    assert abs(second.json()["traces"][0]["total_cost"] - 0.0009) < 1e-12


def test_reingest_reprices_with_the_latest_effective_price(client, session_factory, project):
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        _add_price(session, amount_in=0.10, amount_out=0.20, effective_from=now - timedelta(hours=2))
    client.post("/api/v1/traces", content=build_request(_trace(904, now)), headers=_headers())

    with session_factory() as session:
        _add_price(session, amount_in=0.30, amount_out=0.60, effective_from=now - timedelta(minutes=30))
    again = client.post("/api/v1/traces", content=build_request(_trace(904, now)), headers=_headers())
    assert abs(again.json()["traces"][0]["total_cost"] - 0.0009) < 1e-12
