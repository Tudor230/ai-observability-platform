"""Search + sort params on /executions, /alerts and /pricing (audit item 4)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from helpers import (
    build_request,
    build_span,
    seed_department,
    seed_project,
    seed_team,
    seed_user,
)

from aiobs_backend.models import Alert

KEY = "test-key"
BASE = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)


def _headers(project: str = "proj-1", key: str = KEY):
    return {"x-project-name": project, "authorization": f"Bearer {key}"}


def _trace(
    index: int,
    *,
    workflow: str,
    start: datetime,
    duration_ms: int = 1000,
    completion_tokens: int = 100,
    error: str | None = None,
    project: str = "proj-1",
):
    root = build_span(
        name=workflow,
        oi_kind="CHAIN",
        span_id=1,
        trace_id=3000 + index,
        start=start,
        end=start + timedelta(milliseconds=duration_ms),
        status=2 if error else 0,
        status_message=error or "",
        attrs={"sdk.project_id": project, "sdk.client_id": "client-42"},
    )
    llm = build_span(
        name="llm_call",
        oi_kind="LLM",
        span_id=2,
        trace_id=3000 + index,
        parent_span_id=1,
        start=start + timedelta(milliseconds=10),
        end=start + timedelta(milliseconds=duration_ms),
        status=2 if error else 0,
        status_message=error or "",
        attrs={
            "llm.model_name": "gpt-4o-mini",
            "llm.provider": "openai",
            "llm.token_count.prompt": 100,
            "llm.token_count.completion": completion_tokens,
        },
    )
    return [root, llm]


def _ingest(client, index: int, **kwargs) -> None:
    resp = client.post(
        "/api/v1/traces",
        content=build_request(_trace(index, **kwargs)),
        headers=_headers(kwargs.get("project", "proj-1")),
    )
    assert resp.status_code == 200, resp.text


def test_execution_q_matches_trace_workflow_and_error(client, project):
    _ingest(client, 1, workflow="checkout-flow", start=BASE)
    _ingest(
        client,
        2,
        workflow="refund-flow",
        start=BASE + timedelta(minutes=1),
        error="API rate limit exceeded (429)",
    )

    q = client.get("/api/v1/executions", params={"q": "checkout"}).json()
    assert [i["workflow"] for i in q["items"]] == ["checkout-flow"]

    q = client.get("/api/v1/executions", params={"q": "refund"}).json()
    assert [i["workflow"] for i in q["items"]] == ["refund-flow"]

    # Error messages are searchable too.
    q = client.get("/api/v1/executions", params={"q": "rate limit"}).json()
    assert q["total"] == 1
    assert q["items"][0]["error_kind"] == "rate_limit"

    assert client.get("/api/v1/executions", params={"q": "no-such-thing"}).json()["total"] == 0


def test_execution_sort_and_order(client, project):
    _ingest(client, 1, workflow="a", start=BASE, duration_ms=3000, completion_tokens=500)
    _ingest(client, 2, workflow="b", start=BASE + timedelta(minutes=1), duration_ms=1000, completion_tokens=100)
    _ingest(
        client,
        3,
        workflow="c",
        start=BASE + timedelta(minutes=2),
        duration_ms=2000,
        completion_tokens=300,
        error="boom",
    )

    tokens = client.get(
        "/api/v1/executions", params={"sort": "total_tokens", "order": "asc"}
    ).json()["items"]
    assert [i["total_tokens"] for i in tokens] == [200, 400, 600]

    durations = client.get(
        "/api/v1/executions", params={"sort": "duration_ms", "order": "desc"}
    ).json()["items"]
    assert [i["duration_ms"] for i in durations] == [3000.0, 2000.0, 1000.0]

    latest = client.get(
        "/api/v1/executions", params={"sort": "started_at", "order": "desc"}
    ).json()["items"]
    assert [i["workflow"] for i in latest] == ["c", "b", "a"]

    errored = client.get(
        "/api/v1/executions", params={"sort": "error_count", "order": "desc"}
    ).json()["items"]
    assert errored[0]["workflow"] == "c"

    assert (
        client.get("/api/v1/executions", params={"sort": "bogus"}).status_code == 422
    )
    assert (
        client.get("/api/v1/executions", params={"order": "sideways"}).status_code == 422
    )


def test_execution_pagination_is_stable_with_equal_timestamps(client, project):
    # Identical started_at: the id tiebreaker must keep pages disjoint.
    for index in range(1, 4):
        _ingest(client, index, workflow=f"wf-{index}", start=BASE)

    first = client.get(
        "/api/v1/executions", params={"limit": 2, "offset": 0}
    ).json()
    second = client.get(
        "/api/v1/executions", params={"limit": 2, "offset": 2}
    ).json()
    ids = [i["id"] for i in first["items"]] + [i["id"] for i in second["items"]]
    assert len(ids) == 3
    assert len(set(ids)) == 3
    assert first["total"] == 3


def test_scoped_search_respects_membership_scope(anon, session_factory):
    with session_factory() as session:
        department = seed_department(session, "Ops")
        team_a = seed_team(session, name="A", department=department)
        team_b = seed_team(session, name="B", department=department)
        seed_project(session, project_id="p1", api_key=KEY, name="P1", team=team_a)
        seed_project(session, project_id="p2", api_key="k2", name="P2", team=team_b)
        _, key = seed_user(
            session, "eng@x", role="engineer", scope_type="team", scope_id=team_a.id
        )
        session.commit()

    _ingest(anon, 1, workflow="shared-name", start=BASE, project="p1")
    anon.post(
        "/api/v1/traces",
        content=build_request(_trace(2, workflow="shared-name", start=BASE, project="p2")),
        headers=_headers(project="p2", key="k2"),
    )

    body = anon.get(
        "/api/v1/executions", params={"q": "shared"}, headers={"x-api-key": key}
    ).json()
    assert body["total"] == 1
    assert body["items"][0]["project_id"] == "p1"


def test_alert_search_and_sort(client, session_factory):
    with session_factory() as session:
        session.add_all(
            [
                Alert(rule_id="r1", severity="warning", message="Daily token consumption high", dimension="rule"),
                Alert(rule_id="r2", severity="critical", message="Budget exceeded: monthly", dimension="budget"),
                Alert(rule_id="r3", severity="warning", message="P95 latency spike", dimension="rule"),
            ]
        )
        session.commit()

    q = client.get("/api/v1/alerts", params={"q": "budget"}).json()
    assert q["total"] == 1

    asc = client.get(
        "/api/v1/alerts", params={"sort": "severity", "order": "asc"}
    ).json()["items"]
    assert [a["severity"] for a in asc] == ["critical", "warning", "warning"]

    assert (
        client.get("/api/v1/alerts", params={"sort": "bogus"}).status_code == 422
    )


def test_pricing_search_and_sort(client):
    body = client.get("/api/v1/pricing", params={"q": "gpt"}).json()
    assert body["total"] >= 2
    assert all("gpt" in f"{p['provider']} {p['model']}".lower() for p in body["items"])

    by_model = client.get(
        "/api/v1/pricing", params={"sort": "model", "order": "desc"}
    ).json()["items"]
    assert by_model == sorted(by_model, key=lambda p: p["model"], reverse=True)

    assert client.get("/api/v1/pricing", params={"sort": "bogus"}).status_code == 422
