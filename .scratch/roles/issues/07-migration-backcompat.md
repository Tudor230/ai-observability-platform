# 07 — Migration & back-compat

Type: grilling
Status: resolved
Blocked by: 01, 03

## Question

How do we migrate, and what survives?

Decide:
- The alembic migration: add `departments`, `memberships`, `requests`;
  add `teams.department_id` and `users.password_hash` + `users.token_version`.
- Backfill: legacy teams → a default "General" department; existing users →
  global memberships mapped from their old role (`sdm`→manager, `finance`→exec,
  `engineer`→engineer, `admin`→admin).
- Whether `users.role` is dropped or deprecated after backfill.
- Fate of the admin-key endpoints (`users.py`, `projects.py`) vs the new
  request flow.
- Removal of demo open-reads (`AIOBS_READ_API_KEY` unset) and the dead
  `require_read_access`, per 06; existing RBAC tests
  (`test_rbac.py`, `test_read_access.py`) must be reworked accordingly.
- Updated demo seed incl. bootstrap admin provisioning (see 04).

## Answer

Decided: a **single destructive alembic revision** — hard reset, no backfill.

- **Drop** (FK-safe order): `alerts`, `budgets`, `daily_metrics`,
  `cost_records`, `spans`, `executions`, `workflows`, `agents`, `clients`,
  `projects`, `teams`, and all `users` rows. Pricing is configuration and is
  kept. Legacy team names and user API keys are lost with them.
- **Schema**: create `departments`, `memberships`, `requests`; add
  `teams.department_id`; alter `users` — add `password_hash` and
  `token_version`, drop `role` (per 03).
- **No backfill**: legacy teams/users are dropped, not migrated; the org tree
  starts empty and is built through the request flow.
- **Admin endpoints survive with dual auth**: `x-admin-key` still works
  (machine/bootstrap/scripts) and a session belonging to an `admin` user is
  accepted on the same endpoints.
- **Bootstrap admin**: optional idempotent env seed (`AIOBS_ADMIN_EMAIL` +
  `AIOBS_ADMIN_PASSWORD`) at startup; docker-compose ships dev defaults.
- **Demo seed**: `seed_demo_project` must create a department + team under the
  new model (implementation note).
- RBAC tests (`test_rbac.py`, `test_read_access.py`) and `conftest` seeds are
  reworked accordingly; note tests build schema via `create_all`, so the
  migration itself is not exercised by the suite.