# ADR-0012: Project identifiers are generated; the name is the handle

Status: Accepted

## Context

`projects` carries three identifiers (`models.py`): an internal `id` (32-hex
primary key, used by foreign keys and membership scopes), an external
`project_id` (unique, user-supplied at creation through the create-project
request or the admin `POST /projects`), and a `name` (free-form display label,
not unique). The external `project_id` leaked everywhere in the dashboard: page
titles, table cells, filter chips, picker labels and the create-project form's
slug field, always rendered as `project_id · name` to disambiguate.

The identifier is load-bearing — it is the URL token for project routes and key
management, the read filter (`?project_id=`), the `x-project-name` assertion,
the `daily_metrics` dimension key and the budget/membership project reference —
but the *choice* of value was never meaningful to users, and asking them to type
it produced both friction and inconsistency (slugs like `demo`, `proj-e2e`,
`live-1790602525`).

## Decision

- **`project_id` is server-generated**: `p_` + 12 lowercase hex, assigned where
  the row is created (admin create and request approval). Users never choose it.
- **It is never rendered by the dashboard.** The FE keeps using it as the
  technical token in URLs and API payloads (no client-facing API change), but
  every visible surface shows the project **name**.
- **`name` becomes the unique human handle** — globally unique, enforced by a
  unique index; a duplicate create is rejected with 409. Pickers, chips, tables
  and titles all use it, so no `name · name` disambiguation is needed.
- **The SDK keeps `project_id` only as a debug/test override.** It stays in
  `init()`/env, keeps sending `x-project-name` and the
  `openinference.project.name` resource attribute for Phoenix routing, and is
  documented and warned as not-for-production — production integrators use the
  API key alone (ADR-0008). The bundled examples pass keys only. No
  `project_name` parameter is introduced; `client_id` is removed outright
  (ADR-0011).
- Execution payloads gain `project_name` so the dashboard can render the handle
  without ever falling back to the generated id.

## Consequences

- Create-project flows get shorter: `{name, team_id}` (self-service) and
  `{name, team/department names}` (admin) — the slug field and its validation
  disappear from the dashboard.
- Renaming a project stays impossible for now (no PATCH route); the name is
  fixed at creation, so its uniqueness is a creation-time constraint. If
  renaming is added later it must preserve uniqueness.
- Existing rows keep their current external ids; only new projects get
  generated ones. The mixed shapes (`demo`, `p_…`) are invisible to users.
- The generated id is not a secret and remains readable through the API and URL
  bar; this decision is about UI cleanliness and identity hygiene, not
  confidentiality.
- Support/debugging flows that relied on reading a project id from the UI must
  read it from the API (`GET /api/v1/projects`) or the dashboard URL instead.

## References

- ADR-0008 — the ingest API key is the project identity
- ADR-0011 — retire the client attribution dimension
- `.scratch/refinements-v3/spec.md`
