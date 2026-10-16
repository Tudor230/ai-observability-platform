"""Model insights (phoenix insights 03): per provider·model cost, tokens, latency."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from helpers import (
    STATUS_ERROR,
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


def _payload(
    trace_id: int,
    *,
    project: str = "proj-1",
    model: str = "gpt-4o-mini",
    provider: str = "openai",
    prompt: int = 1000,
    completion: int = 500,
    error: bool = False,
    workflow: str = "checkout",
    duration_ms: int = 100,
):
    now = datetime.now(timezone.utc)
    llm_kwargs = {"status": STATUS_ERROR} if error else {}
    return build_request(
        [
            build_span(
                name=workflow,
                oi_kind="CHAIN",
                span_id=1,
                trace_id=trace_id,
                start=now,
                end=now + timedelta(seconds=1),
                attrs={"sdk.project_id": project},
            ),
            build_span(
                name="llm_call",
                oi_kind="LLM",
                span_id=2,
                trace_id=trace_id,
                parent_span_id=1,
                start=now,
                end=now + timedelta(milliseconds=duration_ms),
                attrs={
                    "llm.model_name": model,
                    "llm.provider": provider,
                    "llm.token_count.prompt": prompt,
                    "llm.token_count.completion": completion,
                },
                **llm_kwargs,
            ),
        ]
    )


def test_models_merge_billing_rows_and_span_traffic(client, project):
    client.post("/api/v1/traces", content=_payload(3001), headers=_headers())
    client.post(
        "/api/v1/traces", content=_payload(3002, error=True, duration_ms=300), headers=_headers()
    )
    client.post(
        "/api/v1/traces",
        content=_payload(3003, model="gpt-4o", prompt=200, completion=100),
        headers=_headers(),
    )

    items = client.get("/api/v1/models").json()["items"]
    by_key = {item["key"]: item for item in items}
    mini = by_key["openai:gpt-4o-mini"]
    assert mini["calls"] == 2
    assert mini["failed_calls"] == 1
    assert mini["error_rate"] == 0.5
    assert mini["executions"] == 2
    assert mini["input_tokens"] == 2000
    assert mini["output_tokens"] == 1000
    assert mini["total_tokens"] == 3000
    # $0.15/M in, $0.60/M out, billed twice.
    assert abs(mini["total_cost"] - 0.0009) < 1e-9
    assert mini["avg_duration_ms"] == 200.0
    assert mini["p95_duration_ms"] >= mini["avg_duration_ms"]
    assert mini["last_seen"]

    gpt4o = by_key["openai:gpt-4o"]
    assert gpt4o["calls"] == 1
    assert abs(gpt4o["total_cost"] - (200 * 2.5 + 100 * 10.0) / 1_000_000) < 1e-9
    # Cost descending: the expensive model leads.
    assert [item["key"] for item in items] == ["openai:gpt-4o", "openai:gpt-4o-mini"]


def _seed_two_project_readers(session):
    """Two teams, one project each, one engineer key per team."""
    department = seed_department(session, "Ops")
    team_a = seed_team(session, name="A", department=department)
    team_b = seed_team(session, name="B", department=department)
    seed_project(session, project_id="proj-1", api_key="k1", name="P1", team=team_a)
    seed_project(session, project_id="proj-2", api_key="k2", name="P2", team=team_b)
    _, key_a = seed_user(
        session, "a@x", role="engineer", scope_type="team", scope_id=team_a.id
    )
    _, key_b = seed_user(
        session, "b@x", role="engineer", scope_type="team", scope_id=team_b.id
    )
    session.commit()
    return key_a, key_b


def test_models_are_scoped_per_project(anon, session_factory):
    with session_factory() as session:
        key_a, key_b = _seed_two_project_readers(session)

    anon.post(
        "/api/v1/traces", content=_payload(3101), headers=_headers("proj-1", "k1")
    )
    anon.post(
        "/api/v1/traces",
        content=_payload(3102, project="proj-2", model="gpt-4o"),
        headers=_headers("proj-2", "k2"),
    )

    scoped = anon.get("/api/v1/models", headers={"x-api-key": key_a}).json()["items"]
    assert [item["key"] for item in scoped] == ["openai:gpt-4o-mini"]
    assert scoped[0]["calls"] == 1

    other = anon.get("/api/v1/models", headers={"x-api-key": key_b}).json()["items"]
    assert [item["key"] for item in other] == ["openai:gpt-4o"]


def test_clients_do_not_see_model_cost(anon, session_factory):
    with session_factory() as session:
        project = seed_project(session, project_id="p1", api_key="k1", name="P1")
        _, client_key = seed_user(
            session, "cli@x", role="client", scope_type="project", scope_id=project.id
        )
        session.commit()

    anon.post(
        "/api/v1/traces",
        content=_payload(3201, project="p1"),
        headers={"x-project-name": "p1", "authorization": "Bearer k1"},
    )

    items = anon.get("/api/v1/models", headers={"x-api-key": client_key}).json()["items"]
    assert items
    assert "total_cost" not in items[0]
    assert items[0]["total_tokens"] == 1500


def test_models_empty_window(client):
    assert client.get(
        "/api/v1/models", params={"start": "2020-01-01", "end": "2020-01-02"}
    ).json() == {"items": [], "total": 0}
