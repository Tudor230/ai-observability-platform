"""Margin (margin 03): versioned proration, coverage, break-even (ADR-0013)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from helpers import build_request, build_span, seed_project, seed_team, seed_user

from aiobs_backend.models import Pricing

# 2026-10-01 .. 2026-10-10 inclusive: proration is per calendar day, and
# `month ≡ 365/12` days (ADR-0013), so a 300/month version pays 9.863014/day.
DAILY_300 = 300 * 12 / 365
DAILY_600 = 600 * 12 / 365


def _seed_past_pricing(session) -> None:
    """Conftest pricing is effective 'now'; this window is in the past."""
    session.add(
        Pricing(
            provider="openai",
            model="gpt-4o-mini",
            model_match="exact",
            input_price_per_1m=0.15,
            output_price_per_1m=0.60,
            effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    )
    session.commit()


def _exec_key(session, email: str = "exec@margin") -> str:
    _, key = seed_user(session, email, role="exec", scope_type="global")
    session.commit()
    return key


def _headers(key: str) -> dict:
    return {"x-api-key": key}


def _ingest_llm(anon, *, project: str, key: str, trace_id: int, day: datetime) -> None:
    """One priced LLM execution on `day` ($0.00045 for 1000/500 gpt-4o-mini)."""
    payload = build_request(
        [
            build_span(
                name="checkout",
                oi_kind="CHAIN",
                span_id=1,
                trace_id=trace_id,
                start=day,
                end=day + timedelta(seconds=1),
                attrs={"sdk.project_id": project},
            ),
            build_span(
                name="llm_call",
                oi_kind="LLM",
                span_id=2,
                trace_id=trace_id,
                parent_span_id=1,
                start=day,
                end=day + timedelta(milliseconds=100),
                attrs={
                    "llm.model_name": "gpt-4o-mini",
                    "llm.provider": "openai",
                    "llm.token_count.prompt": 1000,
                    "llm.token_count.completion": 500,
                },
            ),
        ]
    )
    response = anon.post(
        "/api/v1/traces",
        content=payload,
        headers={"x-project-name": project, "authorization": f"Bearer {key}"},
    )
    assert response.status_code == 200, response.text


def _oct(day: int) -> datetime:
    return datetime(2026, 10, day, 12, 0, tzinfo=timezone.utc)


def _two_projects(session):
    """proj-1 (rated) and proj-2 (unrated, but spending)."""
    team = seed_team(session, name="Margin")
    seed_project(session, project_id="proj-1", api_key="k1", name="Rated", team=team)
    seed_project(session, project_id="proj-2", api_key="k2", name="Unrated", team=team)
    session.commit()


def _rate(anon, key: str, *, amount: float, effective_from: str) -> None:
    created = anon.post(
        "/api/v1/project-rates",
        json={
            "project_id": "proj-1",
            "effective_from": effective_from,
            "revenue_amount": amount,
            "revenue_period": "month",
        },
        headers=_headers(key),
    )
    assert created.status_code == 200, created.text


WINDOW = {"start": "2026-10-01", "end": "2026-10-10"}


def test_margin_prorates_versions_and_counts_uncovered_cost(anon, session_factory):
    with session_factory() as session:
        _two_projects(session)
        _seed_past_pricing(session)
        key = _exec_key(session)

    _rate(anon, key, amount=300, effective_from="2026-10-01")
    _rate(anon, key, amount=600, effective_from="2026-10-06")
    _ingest_llm(anon, project="proj-1", key="k1", trace_id=5001, day=_oct(2))
    _ingest_llm(anon, project="proj-2", key="k2", trace_id=5002, day=_oct(3))

    data = anon.get("/api/v1/margin", params=WINDOW, headers=_headers(key)).json()
    by_project = {item["project_id"]: item for item in data["items"]}
    rated = by_project["proj-1"]
    unrated = by_project["proj-2"]

    # Five days at 300/month, five at 600/month.
    assert rated["covered_days"] == 10
    assert abs(rated["revenue"] - 5 * (DAILY_300 + DAILY_600)) < 1e-6
    assert abs(rated["ai_cost"] - 0.00045) < 1e-9
    assert abs(rated["margin"] - (rated["revenue"] - 0.00045)) < 1e-6
    assert rated["margin_pct"] == round(rated["margin"] / rated["revenue"], 4)
    assert rated["executions"] == 1
    assert abs(rated["cost_per_execution"] - 0.00045) < 1e-9
    # Break-even: how much volume the contribution supports at this unit cost.
    assert abs(rated["break_even_scale"] - rated["revenue"] / 0.00045) < 1
    assert rated["break_even_executions"] > 300_000
    # The rate shown is the version active on the last window day.
    assert rated["rate"]["effective_from"] == "2026-10-06"

    # Unrated: cost is real, margin is unknown — never rendered as $0.
    assert unrated["rate"] is None
    assert unrated["margin"] is None
    assert unrated["covered_days"] == 0
    assert abs(unrated["ai_cost"] - 0.00045) < 1e-9
    assert unrated["margin_pct"] is None
    assert unrated["break_even_scale"] is None

    # Totals are conservative: every AI cost counts, coverage says how much of
    # it has revenue behind it.
    totals = data["totals"]
    assert abs(totals["ai_cost"] - 0.0009) < 1e-9
    assert abs(totals["revenue"] - rated["revenue"]) < 1e-6
    assert abs(totals["margin"] - (totals["revenue"] - totals["ai_cost"])) < 1e-6
    assert totals["projects"] == 2
    assert totals["projects_rated"] == 1
    assert totals["coverage_pct"] == 0.5
    assert abs(totals["covered_cost"] - 0.00045) < 1e-9

    # The daily series steps when the second version starts.
    series = {point["day"]: point for point in data["series"]}
    assert len(data["series"]) == 10
    assert abs(series["2026-10-01"]["revenue"] - DAILY_300) < 1e-6
    assert abs(series["2026-10-05"]["revenue"] - DAILY_300) < 1e-6
    assert abs(series["2026-10-06"]["revenue"] - DAILY_600) < 1e-6
    assert abs(series["2026-10-02"]["ai_cost"] - 0.00045) < 1e-9
    assert data["window"] == {"start": "2026-10-01", "end": "2026-10-10", "days": 10}

    # Worst margin first; unrated projects follow.
    assert data["items"][0]["project_id"] == "proj-1"


def test_margin_without_rates_reports_no_margin_but_keeps_cost(anon, session_factory):
    """The exec added nothing: no fabricated revenue, coverage 0, cost visible."""
    with session_factory() as session:
        _two_projects(session)
        _seed_past_pricing(session)
        key = _exec_key(session)
    _ingest_llm(anon, project="proj-1", key="k1", trace_id=5101, day=_oct(2))

    data = anon.get("/api/v1/margin", params=WINDOW, headers=_headers(key)).json()
    item = data["items"][0]
    assert item["rate"] is None
    assert item["margin"] is None
    assert item["revenue"] == 0
    assert abs(item["ai_cost"] - 0.00045) < 1e-9

    totals = data["totals"]
    assert totals["revenue"] == 0
    assert totals["manual_cost"] == 0
    assert totals["margin_pct"] is None
    assert totals["projects_rated"] == 0
    assert totals["coverage_pct"] == 0.0
    # Conservative: the spend still counts against the (zero) revenue.
    assert abs(totals["margin"] + totals["ai_cost"]) < 1e-9


def test_margin_manual_cost_reduces_the_contribution(anon, session_factory):
    with session_factory() as session:
        _two_projects(session)
        _seed_past_pricing(session)
        _seed_past_pricing(session)
        key = _exec_key(session)

    created = anon.post(
        "/api/v1/project-rates",
        json={
            "project_id": "proj-1",
            "effective_from": "2026-10-01",
            "revenue_amount": 300,
            "revenue_period": "month",
            "manual_cost_amount": 100,
            "manual_cost_period": "month",
        },
        headers=_headers(key),
    )
    assert created.status_code == 200, created.text
    _ingest_llm(anon, project="proj-1", key="k1", trace_id=5201, day=_oct(2))

    item = anon.get("/api/v1/margin", params=WINDOW, headers=_headers(key)).json()["items"][0]
    assert abs(item["revenue"] - 10 * DAILY_300) < 1e-6
    assert abs(item["manual_cost"] - 10 * (100 * 12 / 365)) < 1e-6
    assert abs(item["margin"] - (item["revenue"] - item["manual_cost"] - item["ai_cost"])) < 1e-6
    assert abs(item["break_even_scale"] - (item["revenue"] - item["manual_cost"]) / item["ai_cost"]) < 1


def test_margin_is_exec_only(anon, session_factory, project):
    with session_factory() as session:
        _, manager_key = seed_user(
            session,
            "mgr@margin",
            role="manager",
            scope_type="team",
            scope_id=project.team_id,
        )
        _, client_key = seed_user(
            session, "cli@margin", role="client", scope_type="project", scope_id=project.id
        )
        session.commit()

    assert anon.get("/api/v1/margin", headers=_headers(manager_key)).status_code == 403
    assert anon.get("/api/v1/margin", headers=_headers(client_key)).status_code == 403


def test_margin_empty_window(anon, session_factory, project):
    with session_factory() as session:
        key = _exec_key(session)
    data = anon.get(
        "/api/v1/margin",
        params={"start": "2020-01-01", "end": "2020-01-02"},
        headers=_headers(key),
    ).json()
    assert data["items"] == []
    assert data["totals"]["projects"] == 0
    assert data["totals"]["coverage_pct"] == 0.0
    assert len(data["series"]) == 2


def test_internal_projects_are_reported_but_never_scored_as_a_loss(anon, session_factory):
    """Internal work needs no revenue: its cost is reported apart, not as margin."""
    with session_factory() as session:
        _two_projects(session)
        _seed_past_pricing(session)
        key = _exec_key(session)

    _rate(anon, key, amount=300, effective_from="2026-10-01")
    flagged = anon.patch(
        "/api/v1/project-rates/proj-2/internal",
        json={"internal": True},
        headers=_headers(key),
    )
    assert flagged.status_code == 200, flagged.text
    assert flagged.json()["internal"] is True
    # A version on an internal project is ignored — the flag wins.
    anon.post(
        "/api/v1/project-rates",
        json={
            "project_id": "proj-2",
            "effective_from": "2026-10-01",
            "revenue_amount": 500,
        },
        headers=_headers(key),
    )
    _ingest_llm(anon, project="proj-1", key="k1", trace_id=5301, day=_oct(2))
    _ingest_llm(anon, project="proj-2", key="k2", trace_id=5302, day=_oct(3))

    data = anon.get("/api/v1/margin", params=WINDOW, headers=_headers(key)).json()
    by_project = {item["project_id"]: item for item in data["items"]}
    internal = by_project["proj-2"]
    assert internal["internal"] is True
    assert internal["margin"] is None
    assert internal["revenue"] == 0
    assert internal["covered_days"] == 0
    assert abs(internal["ai_cost"] - 0.00045) < 1e-9

    totals = data["totals"]
    assert abs(totals["ai_cost"] - 0.00045) < 1e-9  # external work only
    assert abs(totals["internal_cost"] - 0.00045) < 1e-9  # reported separately
    assert totals["coverage_pct"] == 1.0  # every external cost has revenue
    assert totals["projects"] == 1
    assert totals["internal_projects"] == 1
    assert totals["projects_rated"] == 1

    # Internal rows sort last and never join the margin line.
    assert data["items"][-1]["project_id"] == "proj-2"
    series = {point["day"]: point for point in data["series"]}
    assert abs(series["2026-10-03"]["internal_cost"] - 0.00045) < 1e-9
    assert series["2026-10-03"]["ai_cost"] == 0
    # The margin line carries the external revenue accrual only — internal spend
    # sits in its own bucket and never touches it.
    assert series["2026-10-03"]["margin"] == series["2026-10-03"]["revenue"]
    assert series["2026-10-03"]["margin"] > 0
