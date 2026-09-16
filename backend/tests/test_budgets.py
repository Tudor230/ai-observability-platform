"""Budget window semantics (F09): spend resets per day/week/month window."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from helpers import build_request, build_span

from aiobs_backend.alerts import budget_window, evaluate_alerts
from aiobs_backend.models import Budget

KEY = "test-key"


def _headers():
    return {"x-project-name": "proj-1", "authorization": f"Bearer {KEY}"}


def _trace(trace_id: int, start: datetime):
    root = build_span(
        name="checkout", oi_kind="CHAIN", span_id=1, trace_id=trace_id,
        start=start, end=start + timedelta(seconds=1),
        attrs={"sdk.project_id": "proj-1", "sdk.client_id": "client-42"},
    )
    llm = build_span(
        name="llm_call", oi_kind="LLM", span_id=2, trace_id=trace_id, parent_span_id=1,
        start=start + timedelta(milliseconds=100), end=start + timedelta(seconds=1),
        attrs={"llm.model_name": "gpt-4o-mini", "llm.provider": "openai",
               "llm.token_count.prompt": 1000, "llm.token_count.completion": 500},
    )
    return [root, llm]


def test_budget_window_day():
    now = datetime(2026, 2, 15, 12, 30, tzinfo=timezone.utc)
    budget = Budget(amount=1, period=datetime(2020, 1, 1, tzinfo=timezone.utc),
                    period_type="day")
    start, end = budget_window(budget, now)
    assert start == datetime(2026, 2, 15, tzinfo=timezone.utc)
    assert end == datetime(2026, 2, 16, tzinfo=timezone.utc)


def test_budget_window_week():
    now = datetime(2026, 2, 15, 12, 30, tzinfo=timezone.utc)
    budget = Budget(amount=1, period=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    period_type="week")
    start, end = budget_window(budget, now)
    assert start == datetime(2026, 2, 12, tzinfo=timezone.utc)
    assert end == datetime(2026, 2, 19, tzinfo=timezone.utc)


def test_budget_window_month_clamps_anchor_day():
    """A 31st anchor still yields a window containing `now` in February."""
    now = datetime(2026, 2, 15, 12, 30, tzinfo=timezone.utc)
    budget = Budget(amount=1, period=datetime(2026, 1, 31, 8, 0, tzinfo=timezone.utc),
                    period_type="month")
    start, end = budget_window(budget, now)
    assert start == datetime(2026, 1, 31, 8, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 2, 28, 8, 0, tzinfo=timezone.utc)
    assert start <= now < end


def test_monthly_budget_excludes_previous_month(client, session_factory, project):
    now = datetime.now(timezone.utc)
    first_this_month = now.replace(day=1, hour=12, minute=0, second=0, microsecond=0)
    prev_month = (first_this_month - timedelta(days=1)).replace(
        day=1, hour=12, minute=0, second=0, microsecond=0
    )
    client.post("/api/v1/traces", content=build_request(_trace(801, prev_month)), headers=_headers())
    client.post("/api/v1/traces", content=build_request(_trace(802, now)), headers=_headers())

    created = client.post(
        "/api/v1/budgets",
        json={"name": "monthly", "amount": 1.0, "period": "2020-01-01", "period_type": "month"},
        headers={"x-admin-key": "admin"},
    )
    assert created.status_code == 200, created.text

    status = client.get("/api/v1/budgets/status").json()["items"][0]
    # Only the current month's execution counts (0.00045), not last month's.
    assert abs(status["spend"] - 0.00045) < 1e-9, status
    assert 0 < status["utilization"] < 1
    assert status["period_start"] < status["period_end"]


def test_over_budget_utilization_is_not_clamped(client, session_factory, project):
    now = datetime.now(timezone.utc)
    client.post("/api/v1/traces", content=build_request(_trace(803, now)), headers=_headers())
    client.post(
        "/api/v1/budgets",
        json={"name": "tiny", "amount": 0.0001, "period": "2020-01-01", "period_type": "month"},
        headers={"x-admin-key": "admin"},
    )
    status = client.get("/api/v1/budgets/status").json()["items"][0]
    assert status["utilization"] > 1, status  # 4.5x, must not be clamped here

    with session_factory() as session:
        created = evaluate_alerts(session)
        session.commit()
    assert created, "expected a critical alert"
    alerts = client.get("/api/v1/alerts?status=open").json()["items"]
    assert any(a["severity"] == "critical" for a in alerts)
