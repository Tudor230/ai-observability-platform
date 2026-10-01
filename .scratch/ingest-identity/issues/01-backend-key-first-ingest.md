# 01 — Backend: key-first ingest

Type: task
Status: resolved
Blocked by: —

## Goal

Resolve the ingest project from the Bearer key alone; treat `x-project-name` and
the root's `sdk.project_id` as optional assertions; store the authenticated
project as the root's `sdk.project_id`; fail loudly (409) instead of silently
dropping a fully mismatched batch. Implements ADR-0008.

## Changes

1. **Migration** (`backend/alembic/versions/*_project_keys_unique_hash.py`):
   unique index on `project_keys.key_hash`. If legacy duplicate hashes exist,
   fail with a clear message (should not happen; keys are random).
2. **`backend/src/aiobs_backend/api/deps.py` — `get_project_from_headers`**:
   - Require `authorization: Bearer <key>`; missing/blank → 401.
   - Hash the key (`security.hash_api_key`) and resolve the owning project with
     one query over **active** `project_keys` rows (indexed `key_hash`); no
     match → 401.
   - Disabled project → 403.
   - Update `last_used_at` on the matched key (existing best-effort behavior).
   - If `x-project-name` is present and ≠ `project.project_id` → **409**.
   - Remove the now-unreachable paths: 401 "missing x-project-name", 404
     "unknown project", 401 "project has no API keys yet".
3. **`backend/src/aiobs_backend/ingest/pipeline.py`**:
   - Keep the root mismatch check, but compare against the SDK-sent value
     *before* rewriting.
   - Build stored root attributes as a copy with
     `sdk.project_id = project.project_id` (server-authoritative, always
     overwrite) and use it for root span rows in both storage paths
     (`process_trace` and `_merge_partial_batch`); do not mutate the decoded
     `RawSpan` dicts in place.
4. **`backend/src/aiobs_backend/api/routes/ingest.py` — `_ingest`**:
   - After `process_trace_batch`, if the batch produced summaries and **all** are
     `skipped == "project_mismatch"`, raise `HTTPException(409)` with the trace
     ids and detail before committing. Any accepted trace keeps HTTP 200 with
     the per-trace `skipped` summary.
5. **Docs already updated**: `plans/backend.md` §4, `backend/README.md`,
   `CONTEXT.md`, ADR-0007/0008.

## Acceptance

- Key-only export (no `x-project-name`, no `sdk.project_id`) authenticates and
  creates an execution; the stored root span carries
  `sdk.project_id ==` the key's project.
- Key + matching header/root attr works and stores the authenticated id.
- Key + conflicting header → 409, nothing written.
- Key + conflicting root attr, only trace in batch → 409, nothing written,
  existing rows preserved.
- Mixed batch (one matching trace, one mismatching) → 200; matching trace
  ingested, mismatching trace summarized as `project_mismatch`.
- Unknown/revoked key → 401; disabled project → 403.

## Tests

- Update `backend/tests/test_ingest.py`:
  - `test_project_mismatch_skipped` → single-trace mismatch now expects 409.
  - `test_project_mismatch_preserves_existing_rows` → expects 409 and rows intact.
  - New: key-only ingest, header conflict 409, root attr overwrite, mixed-batch
    200 + partial skip, root detection with no `sdk.project_id`.
- Update `backend/tests/test_projects_keys.py` / `test_read_access.py` /
  `test_scope.py` fixtures that rely on the required `x-project-name` header
  (send the header only where the test is about header semantics).
- Run `uv run pytest` and `uv run ruff check .` in `backend/`; migration runs in
  CI (`alembic upgrade head`).

## Comments

Implemented. `deps.get_project_from_headers` now resolves the project from the
Bearer key via an indexed lookup on `project_keys.key_hash` (new unique index,
migration `f8a2c4d61e07`), rejects conflicting `x-project-name` with 409, and
removes the missing-header/unknown-project/no-keys paths. `pipeline.process_trace`
rewrites the stored root attrs with the authenticated project (mismatch checked
first); `_ingest` answers 409 when every trace in a batch mismatches.
`security.verify_api_key` removed (dead under key-first lookup).

Evidence: `uv run pytest` 106 passed; ruff + mypy clean; migration
upgrade/downgrade on a fresh DB and upgrade on the existing `aiobs` DB; real
HTTP checks for key-only 200, root mismatch 409, header conflict 409, mixed
batch 200 + skip (script output in the session).
