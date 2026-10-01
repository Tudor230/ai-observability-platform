# ai-observability-backend

Agentic Observability and FinOps Platform backend (phase 2). Implements
[`plans/backend.md`](../plans/backend.md): OTLP trace ingest, trace processing,
authoritative failure classification, cost engine + attribution, analytics,
alerts/budgets, and a FastAPI Platform API consumed by the
[dashboard](../plans/frontend.md).

## Development

```bash
uv sync --group dev
export AIOBS_JWT_SECRET=dev-secret-0123456789abcdef   # required by app + alembic
uv run ruff check .    # lint (E/F/I subset)
uv run pytest          # needs Postgres; default DSN aiobs_test on :5432
uv run alembic upgrade head   # schema migrations (fresh database)
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

Schema migrations live in `alembic/`. The Docker stack runs
`alembic upgrade head` before starting the API (Alembic is authoritative);
local runs additionally call `create_all()` as a development fallback. Pricing
is seeded on startup. Seed a demo department + team + project/key with:

```bash
uv run python -c "from aiobs_backend import db, seed; db.create_all(); print(seed.seed_demo_project('proj-1'))"
```

`AIOBS_JWT_SECRET` is required; the API refuses to start without it. Bootstrap
an admin (idempotent, runs at startup) with `AIOBS_ADMIN_EMAIL` +
`AIOBS_ADMIN_PASSWORD`, then log in via `POST /api/v1/auth/login`.

## Auth, roles and scoping (ADR-0006)

Authorization is membership-based; see
[`plans/roles.md`](../plans/roles.md) and
[`docs/adr/0006-membership-rbac-jwt-sessions.md`](../docs/adr/0006-membership-rbac-jwt-sessions.md).

- **Login**: email + password (`POST /api/v1/auth/login`) sets an httpOnly,
  `SameSite=Lax` JWT cookie (24h sliding TTL; `GET /api/v1/auth/me` refreshes
  it). Mutating requests authenticated by cookie must send
  `x-requested-with: aiobs`. `POST /api/v1/users` (admin) provisions accounts
  and returns a generated password once.
- **Roles**: `admin`, `exec`, `manager`, `engineer`, `client`, each granted
  inside a scope (`global`, `department`, `team`, `project`). Access is the
  union of approved memberships; a scoped caller sees only their projects and
  out-of-scope requests answer 404. Client accounts never receive cost fields.
- **Registration**: org units and memberships are requested through
  `POST /api/v1/requests` and approved by managers covering the scope (admin/exec
  for new departments and manager grants). A request the requester could approve
  is **self-approved and materialized immediately** (admin creating a
  department, covering manager creating a team/project). New departments can
  only be requested by users holding an `admin`, `exec`, or `manager`
  membership — engineers and clients get `403`.
- **Ingest keys (ADR-0007/ADR-0008)**: an approved project starts keyless; any
  engineer/manager member can manage its keys — `GET/POST
  /api/v1/projects/{project_id}/keys`, `POST …/keys/{key_id}/rotate`
  (regenerates in place), `DELETE …/keys/{key_id}` (soft revoke). Keys are
  listed redacted (`••••<hint>`), several may be active, and ingest accepts any
  active key (the plaintext is shown once). The key alone identifies the
  project; `x-project-name` is an optional assertion (conflict → 409), and a
  root whose `sdk.project_id` conflicts with the key is skipped — a batch with
  no acceptable traces answers 409.
- **Accounts (admin)**: `POST /api/v1/users` provisions a login (password shown
  once), `POST /users/{id}/reset-password` rotates it, and
  `POST/DELETE /users/{id}/memberships[/{id}]` grant or revoke memberships
  directly, bypassing the request flow.
- **Service access**: `x-admin-key` and `AIOBS_READ_API_KEY` (as `x-api-key`)
  bypass scoping; user API keys are scoped like sessions.

## Validation

- `uv run pytest` — unit + integration against Postgres (`aiobs_test`), 80% coverage floor in CI.
- `uv run python scripts/e2e_smoke.py` — seed + ingest + API smoke against `aiobs`.
- `uv run python scripts/kpi_gate.py` — `docs/05` KPIs: runs the real SDK mock
  suite against a live backend and asserts observability coverage, cost
  accuracy, and failure classification (also runs in CI). Refuses to touch a
  non-disposable database unless `AIOBS_KPI_ALLOW_RESET=1`.
- `uv run python scripts/purge_retention.py` — apply `AIOBS_RETENTION_DAYS`.

## Operations environment

| Variable | Effect |
|---|---|
| `AIOBS_JWT_SECRET` | **required** — HS256 signing key for session cookies |
| `AIOBS_JWT_TTL_S` | session lifetime in seconds (default 24h, refreshed on `/auth/me`) |
| `AIOBS_COOKIE_SECURE` | set `true` behind HTTPS (adds `Secure` to the cookie) |
| `AIOBS_ADMIN_EMAIL` / `AIOBS_ADMIN_PASSWORD` | optional bootstrap admin seeded at startup |
| `AIOBS_CORS_ORIGINS` | JSON list of browser origins allowed with credentials |
| `AIOBS_READ_API_KEY` | service read key: `x-api-key` bypasses scoping (reads always require auth) |
| `AIOBS_RETENTION_DAYS` | `>0` deletes executions/spans/costs/metrics/alerts older than the window (`POST /api/v1/maintenance/purge`) |
| `AIOBS_ALERT_WEBHOOK_URL` | POST created alerts as JSON to this webhook (best effort) |
| `AIOBS_MAX_INGEST_BYTES` | OTLP body cap (default 10 MiB; larger bodies get 413) |

## Layout

```
src/aiobs_backend/   the backend (config, db, models, ingest, processing, cost, api)
alembic/             schema migrations
scripts/             e2e smoke + KPI gate
tests/               unit + integration tests
```