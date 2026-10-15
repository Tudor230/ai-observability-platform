# 02 — Backend: generated `project_id`, unique name, `project_name` in payloads

Type: task
Status: resolved
Blocked by: —
Area: refinements v3, project identity (ADR-0012)
Estimate: M

## Goal

Stop asking users for a project id: generate it server-side, make the name the
unique handle, and give the dashboard a name to render instead of the id.

## Changes

1. **`models.py`** — `Project.name` gets `unique=True` (global unique index).
   `Project.project_id` stays `unique=True` but is no longer caller-supplied.
2. **`api/routes/projects.py`**
   - `ProjectIn` drops `project_id` (`{name, team_name, department_name}`);
     `POST /projects` generates `p_<12 hex>` when creating the row and returns
     it in `KeyOut`.
   - Duplicate name → 409 (`project name already exists`); keep the existing
     409 for generated-id collisions impossible-by-construction (assert/retry
     loop is unnecessary, but keep the unique index as the guard).
   - `GET /projects` keeps returning `project_id` (FE technical token) and
     `name`.
3. **Requests flow** (`api/routes/requests.py`)
   - `CreateProjectPayload` drops `project_id`; the pending request stores
     `{name, team_id}`; approval generates the id.
   - Duplicate name at request creation *and* at approval → 409/400 with a
     clear message.
4. **Execution payloads** (`api/serialize.py`, `api/queries.py`)
   - `execution_dict` gains `project_name` (join/fetch alongside the existing
     `project_ext`); `EXTERNAL` grows the project name column so list/detail
     endpoints carry it without extra queries.
5. **Migration** — unique index on `projects.name` (audited: no duplicates in
   the dev database); no data backfill needed (existing ids stay).
6. **Tests** — `tests/test_requests.py` (payload without `project_id`,
   generated value shape `^p_[0-9a-f]{12}$`, duplicate name 409),
   `tests/test_projects*.py` (admin create path), execution payload asserts
   `project_name`.

## Acceptance

- Creating a project (admin or request/approval) requires only a name (plus
  team/department); the response carries a generated `project_id` matching
  `^p_[0-9a-f]{12}$`.
- Two projects cannot share a name, at creation or approval time.
- `GET /api/v1/executions` and the detail endpoint return `project_name`.
- Existing projects keep their ids and keep resolving through every existing
  read path.

## Tests

- `uv run pytest -q`, `ruff`, `mypy`; migration `upgrade head` + `alembic check`
  + `downgrade -1` + re-upgrade on a fresh test database.

## Comments

Done. `security.generate_project_id()` emits `p_<12 hex>`; `Project.name` is
unique (migration `a2f7c1d94b3e`, constraint `uq_projects_name`); `ProjectIn`
and `CreateProjectPayload` dropped `project_id`, and both creation paths (admin
`POST /projects`, request approval) generate it — duplicates are rejected 409
at request time *and* at approval. `EXTERNAL` gained `Project.name` and
`execution_dict` a `project_name` field (list + detail endpoints).

Evidence: full backend suite **145 passed**; `ruff` clean; `mypy` clean on 42
files; migration round-trip on a scratch database (`upgrade head` →
`alembic check` "No new upgrade operations detected" → `downgrade -1` →
`upgrade head`); new coverage in `tests/test_projects_keys.py`
(`test_project_name_is_unique_and_required`, generated-id shape
`^p_[0-9a-f]{12}$` asserted) and `tests/test_requests.py` (name-only payload,
generated id, duplicate 409).
