"""DailyMetric uniqueness + upsert (F26) and team dimension (F25)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from helpers import build_request, build_span
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from aiobs_backend import analytics
from aiobs_backend.models import DailyMetric

KEY = "test-key"


def _headers() -> dict:
    return {"x-project-name": "proj-1", "authorization": f"Bearer {KEY}"}


def _trace(trace_id: int):
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
               "llm.token_count.prompt": 100, "llm.token_count.completion": 50},
    )
    return [root, llm]


def test_rollup_is_idempotent_and_covers_team_dimension(client, session_factory, project):
    client.post("/api/v1/traces", content=build_request(_trace(1400)), headers=_headers())
    with session_factory() as session:
        analytics.rollup_recent(session)
        session.commit()
    with session_factory() as session:
        analytics.rollup_recent(session)
        session.commit()
        rows = session.execute(select(DailyMetric)).scalars().all()

    keys = [(m.day, m.dimension, m.dimension_key) for m in rows]
    assert len(keys) == len(set(keys)), "duplicate metric rows after two rollups"
    dims = {m.dimension for m in rows}
    assert {"total", "project", "client", "workflow", "team"} <= dims
    team_row = next(m for m in rows if m.dimension == "team")
    assert team_row.dimension_key == "Test"  # seed_project's team
    assert team_row.executions == 1


def test_daily_metric_rejects_duplicate_rows(session_factory, project):
    base = dict(day="2026-01-01", dimension="total", dimension_key=None, executions=1)
    with session_factory() as session:
        session.add(DailyMetric(**base))
        session.commit()
        session.add(DailyMetric(**base))
        with pytest.raises(IntegrityError):
            session.commit()


def test_costs_team_dimension(client, project):
    client.post("/api/v1/traces", content=build_request(_trace(1401)), headers=_headers())
    data = client.get("/api/v1/costs?dimension=team").json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["key"] == "Test"  # seed_project's team
    assert abs(item["total_cost"] - 0.000045) < 1e-9
    assert item["executions"] == 1
