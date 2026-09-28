"""Local e2e smoke: start uvicorn against Postgres, ingest a trace, check the API."""
import os
import sys

DSN = os.environ.get(
    "AIOBS_E2E_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/aiobs",
)
# Settings are read at import time (the app factory builds CORS from them).
os.environ["AIOBS_DATABASE_URL"] = DSN
os.environ.setdefault(
    "AIOBS_JWT_SECRET", "e2e-secret-0123456789abcdef0123456789abcdef"
)
os.environ.setdefault("AIOBS_ADMIN_EMAIL", "e2e-admin@local")
os.environ.setdefault("AIOBS_ADMIN_PASSWORD", "e2e-admin-pass")

from fastapi.testclient import TestClient  # noqa: E402

from aiobs_backend import db  # noqa: E402
from aiobs_backend.main import app  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests"))
from helpers import build_request, build_span  # noqa: E402


def main():
    from aiobs_backend.config import get_settings

    get_settings.cache_clear()
    db._engine = None
    db._session_factory = None
    db.create_all()

    # Seed a demo department/team/project + pricing + bootstrap admin.
    from aiobs_backend import seed

    seed.seed_pricing()
    key = seed.seed_demo_project(project_id="proj-e2e", name="E2E Project")
    seed.seed_admin(
        os.environ["AIOBS_ADMIN_EMAIL"], os.environ["AIOBS_ADMIN_PASSWORD"]
    )

    client = TestClient(app)
    headers = {"x-project-name": "proj-e2e", "authorization": f"Bearer {key}"}

    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    root = build_span(
        name="checkout",
        oi_kind="CHAIN",
        span_id=1,
        trace_id=9001,
        start=now,
        end=now + timedelta(seconds=2),
        attrs={
            "sdk.project_id": "proj-e2e",
            "sdk.client_id": "client-99",
            "sdk.workflow_id": "order-e2e",
            "session.id": "order-e2e",
            "metadata": '{"channel": "web"}',
        },
    )
    llm = build_span(
        name="llm",
        oi_kind="LLM",
        span_id=2,
        trace_id=9001,
        parent_span_id=1,
        start=now + timedelta(milliseconds=100),
        end=now + timedelta(seconds=1),
        attrs={
            "llm.model_name": "gpt-4o-mini",
            "llm.provider": "openai",
            "llm.token_count.prompt": 2000,
            "llm.token_count.completion": 300,
            "llm.token_count.total": 2300,
        },
    )
    r = client.post("/api/v1/traces", content=build_request([root, llm]), headers=headers)
    assert r.status_code == 200, r.text
    print("ingest:", r.json())

    # Login as the bootstrap admin; reads now require a session or key.
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": os.environ["AIOBS_ADMIN_EMAIL"],
            "password": os.environ["AIOBS_ADMIN_PASSWORD"],
        },
    )
    assert login.status_code == 200, login.text
    print("login:", login.json()["user"]["email"], login.json()["roles"])

    from aiobs_backend import alerts, analytics

    with db.session_scope() as s:
        analytics.rollup_recent(s)
        created = alerts.evaluate_alerts(s)
        print("alerts created:", created)

    checks = {
        "health": client.get("/health"),
        "me": client.get("/api/v1/auth/me"),
        "overview": client.get("/api/v1/overview"),
        "executions": client.get("/api/v1/executions"),
        "workflows": client.get("/api/v1/workflows"),
        "clients": client.get("/api/v1/clients"),
        "costs-project": client.get("/api/v1/costs?dimension=project"),
        "costs-model": client.get("/api/v1/costs?dimension=model"),
        "metrics": client.get("/api/v1/metrics?dimension=total"),
        "alerts": client.get("/api/v1/alerts"),
        "directory": client.get("/api/v1/projects"),
        "requests": client.get("/api/v1/requests"),
    }
    ok = True
    for name, resp in checks.items():
        status = "OK" if resp.status_code == 200 else f"FAIL({resp.status_code})"
        if resp.status_code != 200:
            ok = False
        print(f"  {name}: {status}")

    # Unauthenticated reads must be rejected (demo open-reads removed).
    anon = TestClient(app)
    rejected = anon.get("/api/v1/executions")
    print("  anon executions:", rejected.status_code)
    if rejected.status_code != 401:
        ok = False

    print("ALL OK" if ok else "SOME CHECKS FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
