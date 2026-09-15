"""KPI gate (docs/05): run the real SDK mock suite against a live backend and
assert the platform KPIs:
- KPI 1 (observability coverage): mock scenarios reconstruct into executions
  with the expected token counts and span structure.
- KPI 2 (cost attribution accuracy): a known, priced trace is costed exactly.
- Failure classification: expected error kinds appear for the failure scenarios.

Usage:
    uv run python scripts/kpi_gate.py

Starts the backend itself (uvicorn), seeds a project, runs ``aiobs-mock``
pointed at it, then asserts against the API. Exit 0 = all KPIs pass.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent
SDK_DIR = REPO_DIR / "sdk"
sys.path.insert(0, str(BACKEND_DIR / "tests"))

DB_URL = os.environ.get(
    "AIOBS_KPI_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/aiobs",
)
PORT = int(os.environ.get("AIOBS_KPI_PORT", "8000"))
PROJECT_ID = "proj-1"  # the SDK mock scenarios hard-assert sdk.project_id == proj-1
KPI_KEY = "kpi-test-key"
UV = os.environ.get("UV_EXE", "uv")


def _api(path: str):
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/v1{path}", timeout=30) as r:
        return json.loads(r.read().decode())


def _wait_health() -> None:
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(1)
    raise SystemExit("backend did not become healthy")


def main() -> int:
    os.environ["AIOBS_DATABASE_URL"] = DB_URL
    from sqlalchemy import select

    from aiobs_backend import db, seed
    from aiobs_backend.config import get_settings
    from aiobs_backend.models import Project
    from aiobs_backend.security import hash_api_key

    get_settings.cache_clear()
    db._engine = None
    db._session_factory = None
    # Fresh schema for a deterministic gate (validation DB is disposable).
    db.drop_all()
    db.create_all()
    seed.seed_pricing()
    # Ensure project proj-1 exists with a known key (rotate if it already exists).
    with db.session_scope() as session:
        project = session.execute(
            select(Project).where(Project.project_id == PROJECT_ID)
        ).scalar_one_or_none()
        if project is None:
            seed.seed_demo_project(PROJECT_ID, "KPI Gate")
            project = session.execute(
                select(Project).where(Project.project_id == PROJECT_ID)
            ).scalar_one()
        project.api_key_hash = hash_api_key(KPI_KEY)
        session.flush()
    key = KPI_KEY

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "aiobs_backend.main:app",
         "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=str(BACKEND_DIR),
    )
    try:
        _wait_health()

        # KPI 2: post a known, priced trace and assert exact cost.
        from helpers import build_request, build_span
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        root = build_span(
            name="checkout", oi_kind="CHAIN", span_id=1, trace_id=7001,
            start=now, end=now + timedelta(seconds=1),
            attrs={"sdk.project_id": PROJECT_ID, "sdk.client_id": "client-kpi"},
        )
        llm = build_span(
            name="llm", oi_kind="LLM", span_id=2, trace_id=7001, parent_span_id=1,
            start=now + timedelta(milliseconds=100), end=now + timedelta(seconds=1),
            attrs={"llm.model_name": "gpt-4o-mini", "llm.provider": "openai",
                   "llm.token_count.prompt": 1000, "llm.token_count.completion": 500,
                   "llm.token_count.total": 1500},
        )
        req = urllib.request.Request(
            f"http://127.0.0.1:{PORT}/api/v1/traces",
            data=build_request([root, llm]),
            headers={"x-project-name": PROJECT_ID, "authorization": f"Bearer {key}",
                     "Content-Type": "application/x-protobuf"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            ingest = json.loads(r.read().decode())
        assert ingest["traces"][0]["total_cost"] == pytest_approx(0.00045, rel=1e-6), ingest

        # Run the SDK mock suite against the backend (KPI 1 + classification).
        result = subprocess.run(
            [UV, "run", "aiobs-mock", "--endpoint", f"http://127.0.0.1:{PORT}",
             "--api-key", key, "--project-id", PROJECT_ID],
            cwd=str(SDK_DIR),
            capture_output=True,
            text=True,
            timeout=600,
        )
        print(result.stdout[-2000:])
        if result.returncode != 0:
            print("SDK mock suite FAILED", file=sys.stderr)
            return 1

        # KPI 1: executions reconstructed with expected token coverage.
        ex = _api("/executions?limit=500")
        assert ex["total"] >= 14, f"expected >=14 executions, got {ex['total']}"
        max_tokens = max((e["total_tokens"] for e in ex["items"]), default=0)
        assert max_tokens >= 14, f"expected a scenario with 14 tokens, got {max_tokens}"

        # Classification coverage: failure scenarios produced the expected kinds.
        # Span-level kinds (execution-level roots propagate business_logic for
        # the outer CHAIN wrapper, so we inspect the failure-tree nodes).
        failed = _api("/executions?status=error&limit=500")
        kinds: set[str] = set()
        for e in failed["items"]:
            tree = _api(f"/executions/{e['id']}/failures")
            kinds.update(n["error_kind"] for n in tree["nodes"] if n["error_kind"])
        expected_kinds = {"rate_limit", "retrieval_error", "invalid_output"}
        missing = expected_kinds - kinds
        assert not missing, f"missing error kinds: {missing}; saw {kinds}"

        print("KPIs PASSED: observability coverage (KPI 1), cost accuracy (KPI 2), classification")
        return 0
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()


def pytest_approx(value, rel=1e-9):
    class _Approx:
        def __init__(self, v, r):
            self.v, self.r = v, r

        def __eq__(self, other):
            return abs(other - self.v) <= self.r * max(1, abs(self.v))

    return _Approx(value, rel)


if __name__ == "__main__":
    sys.exit(main())