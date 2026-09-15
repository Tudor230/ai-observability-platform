# ai-observability-platform

Observability + FinOps platform for agentic AI applications. See
[`docs/01`–`docs/05`](docs/01-problem-definition.md) for the vision and
[`plans/implementation-plan.md`](plans/implementation-plan.md) for the roadmap.

## Status

| Component | Status |
|---|---|
| **SDK** (Python; LangChain + LlamaIndex tracing, failure/usage capture, mock-workflow regression suite) | Implemented — [`sdk/`](sdk/) (see [sdk/README.md](sdk/README.md)) |
| **Backend** (OTLP ingest, trace processing, failure classification, cost engine, analytics, alerts/budgets, FastAPI Platform API) | Implemented — [`backend/`](backend/) (see [backend/README.md](backend/README.md), [plans/backend.md](plans/backend.md)) |
| **Dashboard** (engineering / manager / executive views) | Implemented — [`frontend/`](frontend/) (see [frontend/README.md](frontend/README.md), [plans/frontend.md](plans/frontend.md)) |
| Phoenix deployment | root [`docker-compose.yml`](docker-compose.yml) — Postgres instance shared with the SDK tooling and the backend |

## Getting started (SDK)

Start the shared trace stack first (from the repo root) — Phoenix `:6006` +
Postgres `:5432` (the same instance Phoenix, the backend, and the SDK tooling use):

```bash
docker compose up -d --wait postgres phoenix
```

```bash
cd sdk
uv sync --group dev
uv run pytest                      # offline regression suite
uv run aiobs-mock                  # mock-workflow pass/fail report
uv run aiobs-mock --endpoint http://localhost:6006   # export real traces
uv run python dev/inspect_traces.py                  # inspect traces in Postgres
```

## Getting started (backend + dashboard)

### Full stack with Docker (Postgres + Phoenix + backend + dashboard)

```bash
docker compose up -d --build        # one command, everything
# Phoenix UI: http://localhost:6006
# Backend API: http://localhost:8000  (docs at /docs)
# Dashboard:  http://localhost:8080
```

Load demo data through the running backend:

```bash
cd sdk && uv sync --group dev
# set proj-1's API key (see backend README), then:
uv run aiobs-mock --endpoint http://localhost:8000 --api-key <key> --project-id proj-1
```

### Run the pieces individually

```bash
cd backend
uv sync --group dev
docker compose up -d postgres                    # Postgres on :5432 (creates phoenix + aiobs + aiobs_test)
AIOBS_TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/aiobs_test uv run pytest
uv run python scripts/e2e_smoke.py                      # seed + ingest + API check
uv run python scripts/kpi_gate.py                       # docs/05 KPI validation (needs sdk deps)
uv run aiobs-backend                                    # API on :8000 (docs at /docs)

cd ../frontend
npm install && npm run dev                               # dashboard on :5173 (proxies /api to :8000)
```

The SDK's mock workflows can be pointed straight at the backend ingest
(`POST /api/v1/traces`, headers `x-project-name` + `authorization: Bearer <key>`) —
traces are processed, classified, costed, and appear in the dashboard.