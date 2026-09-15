"""Agents aggregation (F25): cost/tokens counted once per execution."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from helpers import build_request, build_span

KEY = "test-key"


def _headers() -> dict:
    return {"x-project-name": "proj-1", "authorization": f"Bearer {KEY}"}


def test_agent_cost_is_counted_once_per_execution(client, project):
    now = datetime.now(timezone.utc)
    root = build_span(
        name="checkout", oi_kind="CHAIN", span_id=1, trace_id=1300,
        start=now, end=now + timedelta(seconds=1),
        attrs={"sdk.project_id": "proj-1", "sdk.client_id": "client-42"},
    )
    llm = build_span(
        name="llm_call", oi_kind="LLM", span_id=2, trace_id=1300, parent_span_id=1,
        start=now + timedelta(milliseconds=10), end=now + timedelta(seconds=1),
        attrs={"llm.model_name": "gpt-4o-mini", "llm.provider": "openai",
               "llm.token_count.prompt": 1000, "llm.token_count.completion": 500},
    )
    agents = [
        build_span(
            name="assistant", oi_kind="AGENT", span_id=sid, trace_id=1300,
            parent_span_id=1,
            start=now + timedelta(milliseconds=20 + sid),
            end=now + timedelta(milliseconds=900),
        )
        for sid in (3, 4)
    ]
    client.post(
        "/api/v1/traces", content=build_request([root, llm, *agents]), headers=_headers()
    )

    item = client.get("/api/v1/agents").json()["items"][0]
    assert item["executions"] == 1
    assert item["total_tokens"] == 1500  # once, not once per AGENT span
    assert abs(item["total_cost"] - 0.00045) < 1e-9
    assert item["error_rate"] == 0.0
