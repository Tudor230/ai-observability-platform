# 02 — Backend: versioned project rates

Type: task
Status: resolved
Blocked by: 01
Area: margin, config API
Estimate: M

## Goal

Exec-maintained revenue and manual-cost inputs, stored as non-overwriting
versions with an explicit `effective_from`.

## Changes

1. **`models.ProjectRate`** — `project_id` FK, `effective_from` (date),
   `revenue_amount`/`revenue_period`, `manual_cost_amount`/`manual_cost_period`,
   `currency`, `created_at`/`updated_at`/`updated_by`, and
   `UNIQUE (project_id, effective_from)`.
2. **Alembic revision** off `c3d91b7f5a24`.
3. **`api/routes/rates.py`** — `GET /project-rates` (versions grouped by
   project), `POST` (new version), `PATCH /{rate_id}` (edit amounts, periods or
   `effective_from`), `DELETE /{rate_id}`; `require_access("exec")`, 404 for
   unknown project/version, 409 for a duplicate date, 422 for bad amounts or
   periods.
4. **Tests** — create/list/edit/delete, duplicate date 409, edit-into-a-clash
   409, manager/client 403, exec 200, unknown project 404.

## Acceptance

- Two versions can coexist; the same `(project, effective_from)` twice is
  rejected, never overwritten.
- Editing a version's date validates the same uniqueness rule.

## Tests

- `uv run pytest`, `uv run ruff check .`, `uv run mypy src`.

## Result

- `models.ProjectRate` + migration `d4b8e2f7c1a9` (versioned rates) and
  `projects.internal` + migration `e2f5a9c3b7d1`; both apply on the dev DB and
  `alembic check` reports no drift.
- `GET /project-rates` returns every project with its `internal` flag and its
  versions (newest first); `POST` creates a version, `PATCH /{id}` edits one,
  `DELETE /{id}` removes one, `PATCH /{project_id}/internal` flips the flag.
- Clashes are `409` (never an overwrite), unknown projects/versions `404`,
  bad amounts/periods `422`, and every route is exec-only.
- Evidence: `tests/test_project_rates.py` — 5 tests covering versions, the
  clash, edit/delete, the internal flag and the role/validation gates.
