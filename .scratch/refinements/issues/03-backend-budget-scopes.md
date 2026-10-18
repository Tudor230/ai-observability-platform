# 03 — Backend: budget scopes (department/team) + scoped CRUD

Type: task
Status: resolved
Blocked by: —
Area: audit item 5 (budgets)
Estimate: M

## Goal

Let managers create, edit and delete budgets for the org units they cover
(department/team/project), add department/team budget scopes, fix budget
spend/list scoping, and add an update endpoint. Implements the audit fix for
"budgets — manager la departament/echipa/proiect (ale lui)".

## Changes

1. **Model + migration** (`models.py`, one Alembic revision):
   - `Budget.department_id` FK→`departments.id`, nullable, indexed.
   - `Budget.team_id` FK→`teams.id`, nullable, indexed.
   - Existing `project_id|client_id|workflow_name` stay as optional AND-filters.
2. **`api/memberships.py`**
   - New helper returning the caller's allowed org scopes, e.g.
     `allowed_budget_scopes(session, memberships) -> (department_ids, team_ids, all: bool)`;
     `None`/`all` for global grants.
3. **`api/queries.py` — `budget_scope_clause`**
   - Visibility = budget.project_id ∈ allowed projects OR budget.team_id ∈
     allowed teams OR budget.department_id ∈ allowed departments; `None`
     (unrestricted) unchanged. Global budgets (all scope fields NULL) remain
     exec/admin-only.
4. **`alerts.py` — `budget_spend`**
   - When `department_id`/`team_id` is set, join `Project → Team` and filter
     accordingly (AND-combined with project/client/workflow filters). Global
     budgets unchanged (exec/admin only).
5. **`api/routes/budgets.py`**
   - Remove the router-level `get_admin_key` from list/status; keep the admin
     key and admin session as one accepted identity and add session-based
     manager/exec auth:
     - exec (global) + admin: any budget, any scope.
     - manager: only budgets whose department/team/project they cover
       (`covers_scope`); `POST` requires at least one of
       `department|team|project` (client/workflow are additional filters);
       unscoped (global) creation stays exec/admin-only. Out-of-scope
       create/edit/delete → 403; out-of-scope reads filtered silently.
   - New `PATCH /budgets/{id}` (name, amount, period, period_type, scope
     fields) with the same authorization; period changes re-anchor the window.
   - Request/response models gain `department`/`team`; responses add a `scope`
     label (`global|department|team|project|client|workflow`, best-effort) for
     the UI. `budget_status` items also carry the scope.
   - `DELETE` uses scoped authorization instead of admin-only.
6. **Tests** (`tests/test_budgets.py` and a focused new file if cleaner):
   - dept/team spend joins (executions counted only under the budget's unit);
   - manager create inside coverage → 201/200; outside → 403; manager
     unscoped create → 403; exec unscoped create → OK;
   - manager sees only covered budgets in list/status; admin sees all;
   - PATCH authorization + window re-anchor; DELETE authorization;
   - global budget spend unchanged for admin.

## Acceptance

- A department manager can create a budget for their department or one of its
  teams/projects and immediately see its utilization on `/budgets/status`.
- A team manager cannot create a budget for a sibling team (403) and cannot
  see its utilization.
- Department/team budgets compute spend only from executions of the projects
  beneath that unit.
- `PATCH` updates amount/period and reset semantics work per `period_type`.
- Admin endpoints keep working with either `x-admin-key` or an admin session.

## Tests

- New/extended backend tests as listed; `uv run pytest -q`, ruff, mypy;
  migration upgrade/downgrade on a fresh DB.

## Comments

Implemented. `Budget` gained `department_id`/`team_id` (migration
`b3f1c8a97d2e`, indexed FKs); `budget_spend` joins Project→Team for unit-scoped
budgets; `budget_scope_clause` unions project/team/department visibility (global
budgets stay exec/admin-only); `AccessScope` carries the caller's
department/team ids. CRUD moved from admin-only to `require_access("manager",
"exec")` with coverage checks: managers must scope a budget to a
department/team/project they cover (unscoped → 403), exec/admin (any global
grant) stay unrestricted; new `PATCH /budgets/{id}` validates the *resulting*
scope before mutating; responses carry `department`/`team`/`scope` labels.

Evidence: new `tests/test_budget_scopes.py` (4 tests: dept/team spend isolation,
manager create matrix incl. sibling-team 403 and unscoped 403, visibility +
PATCH/DELETE authorization, unknown scope 400). Full backend suite **123
passed**; ruff + mypy clean; migration `upgrade head` + `alembic check` (no
drift) + `downgrade -1` + re-upgrade verified on a fresh database.
