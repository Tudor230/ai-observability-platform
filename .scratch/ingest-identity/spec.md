# Ingest identity: the API key is the project identity

Status: accepted and implemented (grilling session 2026-09-29; implementation 2026-09-30)
Decision record: [`docs/adr/0008-ingest-identity-key-authoritative.md`](../../docs/adr/0008-ingest-identity-key-authoritative.md)

## Why

Project registration made the project API key identify exactly one project, but
the SDK still had to send `x-project-name` and stamp `sdk.project_id`; a
stale/mistyped id plus a valid key returned HTTP 200 with a per-trace
`project_mismatch` skip — invisible in the SDK and silent data loss. This spec
makes the key the sole ingest identity and demotes the project id to an
optional, deprecated routing hint.

## Decisions (settled in grilling)

| # | Decision |
|---|----------|
| 1 | `project_id` stays in the SDK as optional, **deprecated** config (`init` arg + `AI_OBSERVABILITY_PROJECT_ID`); the API key is the sole identity. |
| 2 | `x-project-name` becomes optional backend-side; when present it must match the key's project (409 on conflict). |
| 3 | Stored root spans are **server-authoritative**: ingest always writes the authenticated project's id to `sdk.project_id`. |
| 4 | A root whose asserted `sdk.project_id` conflicts is skipped per trace; a batch with **zero acceptable traces** for this reason answers **409** (non-retryable → the OTel exporter logs it). Partial mismatches stay 200. |
| 5 | The SDK additionally sets the `openinference.project.name` resource attribute when (deprecated) `project_id` is configured; `x-project-name` is still sent for Phoenix. |
| 6 | Keys stay **project-level**; workflow-level keys are rejected (workflows are auto-discovered, read-only; attribution already rides `sdk.workflow_id`). |
| 7 | `project_keys.key_hash` gets a unique index for global key lookup; `last_used_at` behavior unchanged. |

## Current behavior (facts to preserve/change)

- SDK header construction: `sdk/src/ai_observability/_tracing.py:73-81` — header only when `config.project_id`.
- SDK root stamping: `sdk/src/ai_observability/_workflow.py:159-182`; resource attributes today are `service.*` only (`_tracing.py:102-108`).
- Ingest auth: `backend/src/aiobs_backend/api/deps.py:207-241` — requires `x-project-name`, looks up the project, verifies the key against that project's active keys.
- Mismatch: `backend/src/aiobs_backend/ingest/pipeline.py:220-229` — HTTP 200 + `skipped: project_mismatch`.
- Root detection: `pipeline.py:115-119` (CHAIN + `sdk.workflow_id`/`sdk.project_id`/`session.id`, else parentless fallback `:141-143`).
- Stored root attrs: `pipeline.py:347` (`root_a`), merge path `:505`; resource attrs are discarded at decode (`ingest/otlp.py:103-106`).
- Frontend reads `execution.project_id` (from the key), not the span attr (`frontend/src/lib/traceSpans.ts:174`).

## Sequencing

- **01 (backend)** and **02 (SDK)** are independent.
- **03 (end-to-end verification)** is blocked by both.

## Out of scope

- Workflow-level keys or workflow registration (rejected).
- Keys scoped above project level (team/department) — stays fog in `.scratch/roles/map.md`.
- Removing `project_id` from the SDK (future major version, after the deprecation window).
- Resource-attribute routing in the backend (resources are intentionally ignored).
