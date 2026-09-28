# Research 01 — Backend read-surface enumeration

Resolves [01 — Backend read-surface enumeration](../issues/01-backend-read-surface.md).

## Auth dependencies (`api/deps.py`)

- `get_db` (`:17`): plain session.
- `get_admin_key` (`:22-28`): header `x-admin-key` vs `AIOBS_ADMIN_API_KEY`; unset → 503, mismatch → 401.
- `get_project_from_headers` (`:31-51`): ingest auth, `x-project-name` + `authorization: Bearer <project key>`; unknown → 404, disabled → 403, bad key → 401.
- `get_project_scope` (`:54-70`): optional `x-project-name` read scope; unknown scope → 404 (F07 guard).
- `require_read_access` (`:73-93`): **defined but never wired (dead code)**.
- `require_role(*roles)` (`:104-140`): demo-mode open when `AIOBS_READ_API_KEY` unset; admin key or service read key bypass; else resolves User by `x-api-key` → checks `user.role`. `admin` implicitly allowed everywhere; empty `roles` = any enabled user. Does not validate role strings.

## Per-endpoint inventory (all under `/api/v1` unless noted)

| Router | Endpoint(s) | Gate | Scope |
|---|---|---|---|
| agents | GET /agents | `require_role("engineer","sdm")` (`:15`) | `project_id` param or `x-project-name` (`:24-40`) |
| alerts | GET /alerts | `require_role()` any user (`:14`) | **none** (global) |
| alerts | PATCH /alerts/{id} | `get_admin_key` (`:52`) | — |
| budgets | GET/POST /budgets, DELETE /budgets/{id} | `get_admin_key` (`:49,76,100`) | — |
| budgets | GET /budgets/status | `require_role("sdm","finance")` (`:112`) | **none** (global, `:113-139`) |
| clients | GET /clients | `require_role("sdm","finance")` (`:14`) | `project_id` or `x-project-name` (`:23-33`) |
| costs | GET /costs | `require_role("sdm","finance")` (`:16`) | `project_id` or `x-project-name` (`:35-46`) |
| executions | GET /executions | `require_role("engineer","sdm")` (`:15`) | `project_id` or `x-project-name` (`:42-58`) |
| executions | GET /executions/{id}, /{id}/spans, /{id}/failures | router gate + `get_project_scope` | row-hiding via `_scoped_execution` (`:18-33`) |
| ingest | POST /api/v1/traces, /v1/traces | `get_project_from_headers` | project key auth |
| maintenance | POST /metrics/rollup, /alerts/evaluate, /maintenance/purge | `get_admin_key` | — |
| metrics | GET /metrics | `require_role()` + `get_project_scope` (`:13,26`) | `x-project-name` only (no param, `:32-37`) |
| overview | GET /overview | `require_role()` + `get_project_scope` (`:16,66`) | `project_id` or `x-project-name` (`:63-82`); **open_alerts count unscoped** (`:83`) |
| pricing | GET/POST /pricing, DELETE /pricing/{id} | `get_admin_key` | — |
| projects | GET/POST /projects, /{id}/rotate, /disable, /enable | `get_admin_key` | — |
| users | GET/POST /users, /{id}/disable, /enable | `get_admin_key` | — |
| workflows | GET /workflows | `require_role("sdm","finance")` (`:14`) | `project_id` or `x-project-name` (`:23-34`) |

## Role strings

- Only validation: `users.py:18` — `pattern="^(admin|engineer|sdm|finance)$"` (default `engineer`).
- `models.py:67` — `role` column default `"engineer"`, comment `admin|engineer|sdm|finance`.
- `require_role` uses `deps.py:134-138`; `admin` implicit bypass.
- Role→endpoint map today: `("engineer","sdm")` → agents, executions; `("sdm","finance")` → clients, costs, workflows, budgets/status; `()` any-user → alerts list, metrics, overview; admin-key routers → budgets CRUD, pricing, projects, users, maintenance, alerts PATCH.

## Key findings for the plan

1. `project_id` query param and `x-project-name` are interchangeable on every scoped read (`project_id or project_scope`); the query param is **not** membership-checked — the primary hole once membership scoping lands.
2. Unscoped reads: `GET /alerts`, `GET /budgets/status`, and `overview`'s `open_alerts` count.
3. `require_read_access` is dead code — wire or drop during migration.
4. `users.role` used in: `users.py:18` (regex), `users.py:35,54,60` (serialize/create), `deps.py:134,137` (require_role), `models.py:67` (default).
5. Ingest auth is orthogonal to user roles — must not break.
6. Demo mode: reads open when `AIOBS_READ_API_KEY` unset (`deps.py:121-122`, `deps.py:83-84`); admin-key endpoints always require the key.
7. CORS wide open (`main.py:57-62`); `/health` open.