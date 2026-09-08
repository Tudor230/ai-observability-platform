# ai-observability-backend

Agentic Observability and FinOps Platform backend (phase 2). Implements
[`plans/backend.md`](../plans/backend.md): OTLP trace ingest, trace processing,
authoritative failure classification, cost engine + attribution, analytics,
alerts/budgets, and a FastAPI Platform API consumed by the
[dashboard](../plans/frontend.md).

## Development

```bash
uv sync --group dev
uv run pytest
```

## Run against the docker stack (postgres + phoenix)

```bash
docker compose -f dev/docker-compose.yml up -d --wait
uv run aiobs-backend --reload     # http://localhost:8000
```

Seed pricing + a demo project (`uv run aiobs-backend --seed` or call the seed script).

## Layout

```
src/aiobs_backend/   the backend (config, db, models, ingest, processing, cost, api)
dev/                 docker-compose (postgres + phoenix + backend)
tests/               unit + integration tests
```