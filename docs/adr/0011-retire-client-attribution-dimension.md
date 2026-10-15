# ADR-0011: Retire the client attribution dimension in favour of project

Status: Accepted

## Context

The platform shipped with `client` as one of its attribution dimensions
(ADR-0003, ADR-0005): the SDK accepted `client_id` on `workflow(...)`, stamped it
as `sdk.client_id` on the workflow root, and ingest upserted a `clients` row per
free-form external key. Cost, usage and budget surfaces then rolled up by that
dimension: `daily_metrics` had a `client` dimension, `/costs` and `/metrics`
accepted `dimension=client`, `/clients` returned a per-client aggregate, budgets
could be scoped to a client, and the dashboard rendered "Cost by client",
"Clients" and "Cost per client (service)" cards.

Two problems accumulated:

- **The dimension is ungoverned.** `client_id` is a caller-supplied string with
  no registry, no membership and no scope: typos create parallel pseudo-clients,
  and nothing connects a client key to the org tree that governs access
  (ADR-0006).
- **It overlaps project.** Projects are already the unit of ingest identity
  (ADR-0007/ADR-0008), of membership scoping, of budgets and of every read
  filter. In practice one project *is* one client engagement, so the two
  dimensions carry the same information while the client one carries no
  authority over who may see it.

Review feedback (`.scratch/refinements-v3/spec.md`) settled the removal.

## Decision

- **The client dimension is removed end to end.** The SDK no longer accepts
  `client_id` on the workflow API and no longer emits `sdk.client_id`; ingest
  stops upserting clients; `executions.client_id`, `budgets.client_id` and the
  `clients` table are dropped; `daily_metrics` client rows are deleted; the
  `client` dimension disappears from `/costs`, `/metrics` and analytics; the
  `/clients` route is deleted; budgets can no longer be scoped to a client;
  alerts stop filtering budget spend by client.
- **Project takes over every surface.** Dashboard breakdowns that were "by
  client" become "by project", and cost detail views key on the project.
- **This is a destructive change.** One migration drops the schema and the
  retained-attribution rows; historical client attribution is not preserved.
  Same precedent as the ADR-0006 reset — the dimension's data has no owner and
  no scope, so migrating it would invent attribution.
- **The RBAC `client` role is a different concept and is untouched.** The role
  (a project-scoped, read-only, cost-free outsider membership) keeps working
  exactly as specified in ADR-0006 and tightened in refinements v2 (clients are
  provisioned by admins and cannot use the request flow). The word collision is
  why this ADR exists: removing "client" from RBAC would be a separate decision
  with a different justification.

## Consequences

- One attribution vocabulary: project, workflow, agent, team. Cost and usage
  questions have a single answer ("which project?"), and the answer obeys
  membership scoping.
- SDK users lose `client_id=`; this is a breaking change released as
  `sdk-v0.2.0` (ADR-0012 covers the related `project_id` handling).
- Budget scopes become project/department/team (+global exec/admin); existing
  client-scoped budgets cannot survive the migration and are dropped with the
  column.
- Historical comparison of cost "by client" is no longer possible from stored
  data; anything needed for a retro-report must be pulled from backups before
  the migration runs.
- `docs/03`, `docs/05`, `plans/*` and the dashboard copy are updated to drop
  client attribution; `CONTEXT.md` records the retirement in the glossary.

## References

- Supersedes the client dimension in ADR-0003 (dimension rows) and ADR-0005
  (per-client cost/margin scope)
- ADR-0006 — membership RBAC; the client *role* stays
- ADR-0007, ADR-0008 — project keys and key-authoritative ingest identity
- `.scratch/refinements-v3/spec.md`
