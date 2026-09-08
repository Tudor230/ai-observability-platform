"""Local e2e smoke: start uvicorn against Postgres, ingest a trace, check the API."""
import os
import sys
import threading
import time
import urllib.request

from fastapi.testclient import TestClient

from aiobs_backend.main import app
from aiobs_backend import db

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests"))
from helpers import build_request, build_span, seed_project  # noqa: E402

from aiobs_backend.security import hash_api_key  # noqa: E402

DSN = os.environ.get(
    "AIOBS_E2E_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:55432/aiobs",
)


def main():
    os.environ["AIOBS_DATABASE_URL"] = DSN
    from aiobs_backend.config import get_settings
    get_settings.cache_clear()
    db._engine = None
    db._session_factory = None
    db.create_all()

    # Seed a demo project + pricing
    from aiobs_backend import seed
    seed.seed_pricing()
    key = seed.seed_demo_project(project_id="proj-e2e", name="E2E Project")

    client = TestClient(app)
    headers = {"x-project-name": "proj-e2e", "authorization": f"Bearer {key}"}

    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    root = build_span(
        name="checkout", oi_kind="CHAIN", span_id=1, trace_id=9001,
        start=now, end=now + timedelta(seconds=2),
        attrs={"sdk.project_id": "proj-e2e", "sdk.client_id": "client-99",
               "sdk.workflow_id": "order-e2e", "session.id": "order-e2e",
               "metadata": '{"channel": "web"}'},
    )
    llm = build_span(
        name="llm", oi_kind="LLM", span_id=2, trace_id=9001, parent_span_id=1,
        start=now + timedelta(milliseconds=100), end=now + timedelta(seconds=1),
        attrs={"llm.model_name": "gpt-4o-mini", "llm.provider": "openai",
               "llm.token_count.prompt": 2000, "llm.token_count.completion": 300,
               "llm.token_count.total": 2300},
    )
    r = client.post("/api/v1/traces", content=build_request([root, llm]), headers=headers)
    assert r.status_code == 200, r.text
    print("ingest:", r.json())

    from aiobs_backend import analytics, alerts
    with db.session_scope() as s:
        analytics.rollup_recent(s)
        created = alerts.evaluate_alerts(s)
        print("alerts created:", created)

    checks = {
        "health": client.get("/health"),
        "overview": client.get("/api/v1/overview"),
        "executions": client.get("/api/v1/executions"),
        "workflows": client.get("/api/v1/workflows"),
        "clients": client.get("/api/v1/clients"),
        "costs-project": client.get("/api/v1/costs?dimension=project"),
        "costs-model": client.get("/api/v1/costs?dimension=model"),
        "metrics": client.get("/api/v1/metrics?dimension=total"),
        "alerts": client.get("/api/v1/alerts"),
    }
    ok = True
    for name, resp in checks.items():
        status = "OK" if resp.status_code == 200 else f"FAIL({resp.status_code})"
        if resp.status_code != 200:
            ok = False
        print(f"  {name}: {status}")
    print("ALL OK" if ok else "SOME CHECKS FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()