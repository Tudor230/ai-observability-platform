# 01 — Backend: search + sort for executions, alerts, pricing

Type: task
Status: resolved
Blocked by: —
Area: audit item 4 (search / sort)
Estimate: M

## Goal

Add server-side search and sorting to the lists that need it, with whitelisted
enums, stable ordering, and unchanged scoping semantics. No new dependencies.

## Changes

1. **`backend/src/aiobs_backend/api/queries.py`**
   - Extend `exec_rows(...)` with `q: str | None`, `sort: str | None`,
     `order: str | None`.
   - `q`: `ilike(f"%{q}%")` across `Execution.trace_id`,
     `Execution.workflow_name`, `Execution.error_message` (OR).
   - `sort` whitelist map:
     `started_at → Execution.started_at` (default), `duration_ms`,
     `total_cost`, `total_tokens`, `error_count`, `status`.
     Invalid values are rejected in the route (Literal), not here.
   - `order`: `asc|desc` (default `desc`), always append
     `Execution.id.desc()/.asc()` as the stable tiebreaker.
2. **`routes/executions.py` — `list_executions`**
   - Params `q: str | None = Query(default=None, max_length=200)`,
     `sort: Literal["started_at","duration_ms","total_cost","total_tokens","error_count","status"] = "started_at"`,
     `order: Literal["asc","desc"] = "desc"`.
   - Pass through to `exec_rows`; `total` stays the filtered count.
3. **`routes/alerts.py` — `list_alerts`**
   - `q` over `Alert.message`; `sort ∈ {triggered_at (default), severity}`;
     `order`; keep `status|severity|limit|offset`.
4. **`routes/pricing.py` — `list_pricing`**
   - `q` over `provider`/`model`; `sort ∈ {provider (default), model, effective_from}`;
     `order`.
5. All invalid enum values must return **422** (FastAPI `Literal` does this);
   keep the existing 422 style from F32.

## Acceptance

- `GET /executions?q=<trace fragment>` returns only matching rows; `q` also
  matches workflow names and error messages.
- `GET /executions?sort=duration_ms&order=asc` returns ascending durations,
  stable across pages (id tiebreaker).
- `GET /executions?sort=bogus` → 422.
- Scoped callers cannot see out-of-scope rows through search/sort (existing
  `resolve_project_filter`/`ensure_visible` behavior is preserved).
- `GET /alerts?q=budget&sort=severity&order=asc` filters and sorts.
- `GET /pricing?q=gpt&sort=effective_from` filters and sorts (admin only).

## Tests

- New `backend/tests/test_search_sort.py`:
  - executions: `q` by trace_id / workflow / error_message; sort + order per
    allowed key; 422 on unknown sort; pagination stability (two pages, no
    duplicates/skips with equal `started_at`).
  - scoping: a team-scoped manager's `q` search never returns other teams'
    executions.
  - alerts: `q` + sort; pricing: `q` + sort (admin key).
- Run `uv run pytest -q` and `uv run ruff check .` in `backend/`.

## Comments

Implemented. `exec_rows` gained `q` (ILIKE over `trace_id`, `workflow_name`,
`root_error_message`), a whitelisted `sort` map (`started_at|duration_ms|
total_cost|total_tokens|error_count|status`) and `order`, always with an
`id` tiebreaker. `/executions`, `/alerts` (`message`, sort
`triggered_at|severity`) and `/pricing` (`provider|model`, sort
`provider|model|effective_from`) expose the params; invalid enums are 422.

Evidence: new `tests/test_search_sort.py` (6 tests: q by trace/workflow/error,
sort+order for every key, 422s, stable pagination with equal timestamps, scoped
search isolation, alert/pricing search+sort). Full `pytest` 124 passed; ruff +
mypy clean. One pre-existing assertion in `test_ingest.py::test_budget_alert`
depended on undefined same-timestamp ordering (critical alert at `items[0]`);
updated to assert presence now that a stable `id` tiebreaker exists.
