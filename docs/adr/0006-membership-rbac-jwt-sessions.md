# ADR-0006: Membership-based RBAC with JWT sessions, replacing flat roles and the persona switcher

Status: Accepted

## Context

The platform shipped v1 with opt-in, flat RBAC: `users.role` is a free-form
string (`admin|engineer|sdm|finance`), read endpoints are gated by
`require_role(...)` only when `AIOBS_READ_API_KEY` is set, and project scoping
is a caller-supplied `x-project-name`/`project_id` header that is validated for
existence but not for ownership. The dashboard carries a client-side persona
switcher (`all|engineer|manager|executive`) persisted in localStorage. There is
no organization hierarchy (`Team` is a flat name), no membership linking a user
to the data they may see, and no account provisioning or login. `docs/06`
already flags the resulting multi-tenancy trap.

The product needs: Department → Team → Project hierarchy; self-service
registration of org units and memberships routed to a manager for approval;
real roles (`admin`, `exec`, `manager`, `engineer`, `client`); and reads scoped
to the caller's memberships. The wayfinder effort
(`.scratch/roles/map.md`, tickets 01–10) resolved the design decisions; the
implementation plan is [`plans/roles.md`](../../plans/roles.md).

## Decision

- **Roles live in memberships, not on users.** A single `memberships` table
  holds `(user_id, role, scope_type, scope_id, status)` with a polymorphic,
  app-validated scope (`global|department|team|project`). `users.role` is
  dropped. Effective access is the **union** of approved memberships: global →
  all projects; department → its teams' projects; team → its projects; project
  → that project. A partial unique index blocks duplicate active grants.
- **Registration and membership changes are requests.** A `requests` table
  (type + JSONB payload) holds all pending state; approval materializes the
  entity or membership. Approvers are managers whose memberships cover the
  target scope; department creation and manager grants are admin/exec-only, and
  the requester who creates a department becomes its initial (department-scoped)
  manager.
- **Authentication is email/password with a JWT cookie.** PyJWT HS256 +
  bcrypt; httpOnly `SameSite=Lax` cookie, 24h sliding TTL, `sub`/`ver`/`exp`
  claims with `users.token_version` for revocation; roles derived per request
  (never embedded in the token). Accounts are admin-provisioned; an optional
  env seed creates the bootstrap admin. `AIOBS_JWT_SECRET` is required.
- **Reads require a session or user API key and are scoped**; an out-of-scope
  requested project returns 404, lists are filtered silently. The admin key and
  the service read key (`AIOBS_READ_API_KEY`) bypass scoping. Implicit demo
  open-reads are removed. The `client` role is read-only, cost-free (cost fields
  stripped server-side), and cannot manage project keys (ADR-0007).
- **The migration is a destructive reset.** One Alembic revision drops
  trace-derived data and users (pricing is kept), creates the new tables, and
  backfills nothing; the org tree is built through the request flow.
- **The persona switcher is removed.** Navigation is the union of views the
  caller's roles permit, driven by `GET /auth/me`; a full-page login, user menu,
  Requests page, project page, and dedicated client view replace it.

## Consequences

- Authorization is centralized in the `require_access(*roles)` dependency and
  the allowed-project derivation; routers stop carrying bespoke role logic.
- The org hierarchy and memberships become the source of truth for both access
  control and the existing team attribution dimension.
- Ingest auth (`x-project-name` + project Bearer key) is untouched; project
  keys remain the SDK contract (extended to multiple keys per project in
  ADR-0007; the key became the sole ingest identity in ADR-0008), and the
  project→team→department hierarchy
  supplies rollup attribution.
- Existing dev/prod data is destroyed by the migration: traces must be
  re-ingested and all users re-provisioned. Accepted for the prototype; the
  roadmap entry records it.
- Some questions remain open and are recorded as fog in the map: approval
  notifications, membership lifecycle (revocation/reassignment/rename),
  ingest keys scoped above project level, and an admin combined view.

## References

- `.scratch/roles/map.md` — decision map; tickets 01–10 hold the detail
- `plans/roles.md` — implementation plan
- `docs/06-project-audit.md` — the multi-tenancy gap this closes
