"""Tool insights (phoenix insights 03): per-tool calls, failures and latency."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from helpers import (
    STATUS_ERROR,
    STATUS_OK,
    build_request,
    build_span,
    seed_department,
    seed_project,
    seed_team,
    seed_user,
)

KEY = "test-key"


def _headers(project: str = "proj-1", key: str = KEY) -> dict:
    return {"x-project-name": project, "authorization": f"Bearer {key}"}


def _payload(trace_id: int, *, tools, project: str = "proj-1"):
    """`tools` is a list of (tool name | None, error, duration ms) triples."""
    now = datetime.now(timezone.utc)
    spans = [
        build_span(
            name="checkout",
            oi_kind="CHAIN",
            span_id=1,
            trace_id=trace_id,
            start=now,
            end=now + timedelta(seconds=1),
            attrs={"sdk.project_id": project},
        )
    ]
    for index, (name, error, duration_ms) in enumerate(tools, start=2):
        attrs = {"tool.name": name} if name else {}
        spans.append(
            build_span(
                name=name or "web_search",
                oi_kind="TOOL",
                span_id=index,
                trace_id=trace_id,
                parent_span_id=1,
                start=now,
                end=now + timedelta(milliseconds=duration_ms),
                status=STATUS_ERROR if error else STATUS_OK,
                attrs=attrs,
            )
        )
    return build_request(spans)


def test_tools_group_calls_errors_and_latency(client, project):
    client.post(
        "/api/v1/traces",
        content=_payload(
            4001,
            tools=[("search", False, 100), ("search", True, 300), ("calculator", False, 20)],
        ),
        headers=_headers(),
    )

    items = client.get("/api/v1/tools").json()["items"]
    by_name = {item["name"]: item for item in items}
    search = by_name["search"]
    assert search["calls"] == 2
    assert search["failed_calls"] == 1
    assert search["error_rate"] == 0.5
    assert search["executions"] == 1
    assert search["avg_duration_ms"] == 200.0
    assert search["p95_duration_ms"] >= search["avg_duration_ms"]
    assert search["last_seen"]

    calculator = by_name["calculator"]
    assert calculator["calls"] == 1
    assert calculator["failed_calls"] == 0
    assert calculator["error_rate"] == 0.0
    # Call volume descending.
    assert [item["name"] for item in items] == ["search", "calculator"]


def test_tool_spans_fall_back_to_the_span_name(client, project):
    client.post("/api/v1/traces", content=_payload(4101, tools=[(None, False, 50)]), headers=_headers())

    items = client.get("/api/v1/tools").json()["items"]
    assert [item["name"] for item in items] == ["web_search"]


def test_tools_are_scoped_per_project(anon, session_factory):
    with session_factory() as session:
        department = seed_department(session, "Ops")
        team_a = seed_team(session, name="A", department=department)
        team_b = seed_team(session, name="B", department=department)
        seed_project(session, project_id="proj-1", api_key="k1", name="P1", team=team_a)
        seed_project(session, project_id="proj-2", api_key="k2", name="P2", team=team_b)
        _, key_a = seed_user(
            session, "a@x", role="manager", scope_type="team", scope_id=team_a.id
        )
        _, key_b = seed_user(
            session, "b@x", role="manager", scope_type="team", scope_id=team_b.id
        )
        session.commit()

    anon.post(
        "/api/v1/traces",
        content=_payload(4201, tools=[("search", False, 10)]),
        headers=_headers("proj-1", "k1"),
    )
    anon.post(
        "/api/v1/traces",
        content=_payload(
            4202, tools=[("search", False, 10), ("shell", False, 10)], project="proj-2"
        ),
        headers=_headers("proj-2", "k2"),
    )

    scoped = anon.get("/api/v1/tools", headers={"x-api-key": key_a}).json()["items"]
    assert [item["name"] for item in scoped] == ["search"]
    assert scoped[0]["calls"] == 1

    other = anon.get("/api/v1/tools", headers={"x-api-key": key_b}).json()["items"]
    assert {item["name"] for item in other} == {"search", "shell"}


def test_tool_insights_read_like_costs(anon, session_factory):
    """manager (scoped) and exec (global) can read them; clients cannot."""
    with session_factory() as session:
        project = seed_project(session, project_id="p1", api_key="k1", name="P1")
        _, client_key = seed_user(
            session, "cli@x", role="client", scope_type="project", scope_id=project.id
        )
        _, exec_key = seed_user(session, "exec@x", role="exec", scope_type="global")
        session.commit()

    anon.post(
        "/api/v1/traces",
        content=_payload(4301, tools=[("search", False, 10)], project="p1"),
        headers={"x-project-name": "p1", "authorization": "Bearer k1"},
    )

    assert anon.get("/api/v1/tools", headers={"x-api-key": client_key}).status_code == 403
    items = anon.get("/api/v1/tools", headers={"x-api-key": exec_key}).json()["items"]
    assert [item["name"] for item in items] == ["search"]


def test_tools_empty_window(client):
    assert client.get(
        "/api/v1/tools", params={"start": "2020-01-01", "end": "2020-01-02"}
    ).json() == {"items": [], "total": 0}
