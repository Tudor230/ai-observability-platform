# ADR-0008: The ingest API key is the project identity

Status: Accepted

## Context

ADR-0007 shipped multi-key project ingest and stated that "the SDK contract is
unchanged": the SDK sends `authorization: Bearer <api_key>` **and**
`x-project-name: <project_id>` on every OTLP export
(`sdk/src/ai_observability/_tracing.py`), and stamps the same id on the
workflow root as `sdk.project_id` (`_workflow.py`). Ingest required the header
(401 without it), resolved the project from it, then verified the key against
that project's keys and asserted the root's `sdk.project_id` matched
(`backend/src/aiobs_backend/api/deps.py`, `ingest/pipeline.py`).

Project registration made the key itself identify exactly one project, so the
SDK-side project id became redundant for the platform while remaining a
footgun: a valid key plus a stale/mistyped `project_id` returned HTTP 200 with
`skipped: "project_mismatch"` per trace — the SDK never sees it and the traces
vanish. Meanwhile Phoenix routes by `x-project-name` (HTTP only, 15.5.0+) or
the canonical `openinference.project.name` resource attribute, so the header is
not required by every backend the SDK can talk to.

Grilling session (2026-09-29) settled the contract; the implementation plan
lives in `.scratch/ingest-identity/`.

## Decision

- **The API key is the sole ingest identity.** Ingest resolves the project
  from the Bearer key via a global hash lookup over active `project_keys` rows
  (new unique index on `key_hash`). Missing/unknown/revoked key → 401; disabled
  project → 403.
- **`x-project-name` is optional.** When present it must equal the key's
  project; a conflicting header is rejected with 409. The "unknown project"
  404 and "project has no API keys yet" 401 paths disappear.
- **SDK `project_id` stays in `init()`/env but is optional and deprecated.**
  The key identifies the project; `project_id` is kept only for Phoenix
  routing/dev. When set, the SDK sends it as `x-project-name` and also sets the
  `openinference.project.name` resource attribute (canonical, works on any
  Phoenix version and over gRPC), and warns that the option is deprecated.
  Removal is targeted at a future major version; existing configs keep working
  in v1 and nothing is removed now.
- **Stored root identity is server-authoritative.** Ingest always writes the
  authenticated project's id into `sdk.project_id` on stored root spans,
  overwriting the SDK-sent value. A root whose asserted value conflicts with
  the key is skipped (per-trace); if a batch yields zero acceptable traces for
  this reason, ingest returns **409 Conflict** — any 4xx except 429 is
  non-retryable in the OTel HTTP exporter, so the SDK logs a permanent export
  failure instead of silently dropping. Partial mismatches stay per-trace skips
  with HTTP 200.
- **Keys stay project-scoped.** No workflow-level credentials; workflows are
  auto-discovered from ingest and remain read-only. Keys scoped *above* project
  level (team/department) remain future fog (`.scratch/roles/map.md`).
- Backend resource attributes are still discarded at decode; the resource
  attribute exists purely for Phoenix/dev routing.

## Consequences

- Teams configure one secret. `project_id` becomes a deprecated
  Phoenix-routing/debugging option, not an ingest requirement; a wrong value now
  fails loudly (409) and is visible in SDK export logs.
- The key lookup changes from "project's active keys, verify each" to a single
  indexed query; `last_used_at` still updates on the matched row.
- Stored root attributes are uniform whether or not the SDK sent a
  `project_id`, and the frontend continues to read `execution.project_id`
  (sourced from the key), unaffected.
- Partially supersedes ADR-0007 (the "SDK contract is unchanged" sentence);
  the multi-key table, key CRUD, and soft revocation decisions stand.
- Mock-workflow/CLI examples move to key-only invocations; `--project-id`
  remains available for Phoenix.
- Security posture is unchanged: a valid key is a bearer credential either way;
  removing the required header does not widen what a key can write.

## References

- `CONTEXT.md` — glossary (OTLP ingest, workflow root)
- `plans/backend.md` §4, `plans/sdk.md` §4–5
- `.scratch/ingest-identity/spec.md` — implementation spec and tickets
- `docs/adr/0007-multiple-project-keys-and-admin-self-approval.md`
