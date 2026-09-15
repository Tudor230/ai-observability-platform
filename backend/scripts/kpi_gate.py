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
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent
SDK_DIR = REPO_DIR / "sdk"
sys.path.insert(0, str(BACKEND_DIR / "tests"))

DB_URL = os.environ.get(
    "AIOBS_KPI_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/aiobs_test",
)
PORT = int(os.environ.get("AIOBS_KPI_PORT", "8000"))
PROJECT_ID = "proj-1"  # the SDK mock scenarios hard-assert sdk.project_id == proj-1
KPI_KEY = "kpi-test-key"
UV = os.environ.get("UV_EXE", "uv")
ADMIN_KEY = os.environ.get("AIOBS_ADMIN_API_KEY") or "kpi-admin"
os.environ["AIOBS_ADMIN_API_KEY"] = ADMIN_KEY

ANSI = re.compile(r"\x1b\[[0-9;]*m")
SCENARIO_ROW = re.compile(r"^(?P<id>\S+)\s+(?P<fw>\S+)\s+(?P<spans>\d+)\s+(?P<result>PASS|FAIL)\s*$")


def _assert_disposable(db_url: str) -> None:
    """Refuse to wipe a database that does not look disposable.

    The gate drops and recreates the schema; guarding the target prevents
    `uv run python scripts/kpi_gate.py` from destroying dev/demo data. Point
    ``AIOBS_KPI_DATABASE_URL`` at a ``*_test``/``*_kpi`` database, or set
    ``AIOBS_KPI_ALLOW_RESET=1`` to override explicitly.
    """
    name = db_url.rsplit("/", 1)[-1].split("?")[0]
    if name.endswith(("_test", "_kpi")) or os.environ.get("AIOBS_KPI_ALLOW_RESET") == "1":
        return
    raise SystemExit(
        f"refusing to reset database {name!r}: use a disposable database "
        "(name ending in _test/_kpi) or set AIOBS_KPI_ALLOW_RESET=1"
    )


def _api(path: str):
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/v1{path}", timeout=30) as r:
        return json.loads(r.read().decode())


def _api_post(path: str, body: dict | None = None):
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/api/v1{path}",
        data=json.dumps(body or {}).encode(),
        headers={"Content-Type": "application/json", "x-admin-key": ADMIN_KEY},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def _parse_scenario_output(text: str) -> list[dict]:
    """Parse the `aiobs-mock` report table (scenario, framework, spans, result)."""
    rows: list[dict] = []
    for line in ANSI.sub("", text).splitlines():
        match = SCENARIO_ROW.match(line.strip())
        if match:
            rows.append(
                {
                    "id": match.group("id"),
                    "framework": match.group("fw"),
                    "spans": int(match.group("spans")),
                    "passed": match.group("result") == "PASS",
                }
            )
    return rows


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
    _assert_disposable(DB_URL)
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

        # KPI 2 (docs/05 §5.3): post a known, priced trace; assert cost error
        # and business attribution.
        from helpers import build_request, build_span

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
        trace = ingest["traces"][0]
        expected_cost = 0.00045
        cost_error_pct = abs(trace["total_cost"] - expected_cost) / expected_cost * 100
        assert cost_error_pct < 1.0, f"KPI 2 cost error {cost_error_pct:.4f}%"
        detail = _api(f"/executions/{trace['execution_id']}")
        assert detail["client_id"] == "client-kpi", detail
        assert detail["workflow"] == "checkout", detail
        print(f"KPI 2: cost error {cost_error_pct:.4f}% (expected {expected_cost})")

        # Run the SDK mock suite against the backend (KPI 1 + classification).
        mock_started = datetime.now(timezone.utc)
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

        scenarios = _parse_scenario_output(result.stdout)
        assert scenarios, "could not parse the mock scenario report"
        failed_scenarios = [s["id"] for s in scenarios if not s["passed"]]
        assert not failed_scenarios, f"mock scenarios failed: {failed_scenarios}"
        expected_events = sum(s["spans"] for s in scenarios)

        # KPI 1 (docs/05 §5.2): captured events / expected events, measured
        # against the spans the mock suite reported for this run only.
        executions = _api("/executions?limit=500")["items"]
        mock_entries = [
            e
            for e in executions
            if e["started_at"]
            and datetime.fromisoformat(e["started_at"]) >= mock_started
        ]
        assert len(mock_entries) == len(scenarios), (
            f"expected {len(scenarios)} executions from the mock suite, "
            f"got {len(mock_entries)}"
        )
        captured_events = sum(
            _api(f"/executions/{e['id']}/spans")["total"] for e in mock_entries
        )
        coverage = captured_events / expected_events if expected_events else 0.0
        print(f"KPI 1: span coverage {coverage:.1%} ({captured_events}/{expected_events})")
        assert coverage >= 0.95, f"KPI 1 coverage {coverage:.1%} below 95%"

        # Classification coverage: the failure scenarios produced every
        # catalogued kind (docs/05 §5.4; business_logic is the generic wrapper).
        failed = _api("/executions?status=error&limit=500")
        kinds: set[str] = set()
        for e in failed["items"]:
            tree = _api(f"/executions/{e['id']}/failures")
            kinds.update(n["error_kind"] for n in tree["nodes"] if n["error_kind"])
        expected_kinds = {
            "rate_limit", "timeout", "provider_error", "invalid_output", "retrieval_error",
        }
        missing = expected_kinds - kinds
        assert not missing, f"missing error kinds: {missing}; saw {kinds}"

        # docs/05 §5.4: the scripted abnormal-consumption run raises a
        # non-budget alert (error-rate rule on today's executions).
        _api_post("/alerts/evaluate")
        open_alerts = _api("/alerts?status=open")["items"]
        rule_alerts = [a for a in open_alerts if a["dimension"] != "budget"]
        assert rule_alerts, f"expected threshold-rule alerts, got {open_alerts}"

        print(
            "KPIs PASSED: coverage (KPI 1), cost error (KPI 2), classification, "
            "alert rules"
        )
        return 0
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    sys.exit(main())