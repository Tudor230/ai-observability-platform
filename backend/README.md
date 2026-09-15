# ai-observability-backend

Agentic Observability and FinOps Platform backend (phase 2). Implements
[`plans/backend.md`](../plans/backend.md): OTLP trace ingest, trace processing,
authoritative failure classification, cost engine + attribution, analytics,
alerts/budgets, and a FastAPI Platform API consumed by the
[dashboard](../plans/frontend.md).

## Development

```bash
uv sync --group dev
uv run pytest          # needs Postgres; default DSN aiobs_test on :5432
```

## Run against the docker stack (postgres + phoenix + dashboard)

The root [`docker-compose.yml`](../docker-compose.yml) runs the whole platform
(Postgres `:5432`, Phoenix `:6006`, backend `:8000`, dashboard `:8080`):

```bash
docker compose up -d --build
```

To run the backend locally against just the Postgres service:

```bash
docker compose up -d postgres
uv run aiobs-backend                    # http://localhost:8000 (docs at /docs)
```

Schema + pricing seed on startup; migrations live in `alembic/`
(`uv run alembic upgrade head`). Seed a demo project/key with:

```bash
uv run python -c "from aiobs_backend import db, seed; db.create_all(); print(seed.seed_demo_project('proj-1'))"
```

## Validation

- `uv run pytest` — unit + integration against Postgres (`aiobs_test`).
- `uv run python scripts/e2e_smoke.py` — seed + ingest + API smoke against `aiobs`.
- `uv run python scripts/kpi_gate.py` — `docs/05` KPIs: runs the real SDK mock
  suite against a live backend and asserts observability coverage, cost
  accuracy, and failure classification (also runs in CI).

## Layout

```
src/aiobs_backend/   the backend (config, db, models, ingest, processing, cost, api)
alembic/             schema migrations
scripts/             e2e smoke + KPI gate
tests/               unit + integration tests
```