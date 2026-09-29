# 03 — Membership data model

Type: grilling
Status: resolved

## Question

How are role + scope stored?

Settled constraints (from charting): roles engineer/manager/exec/client +
admin; multiple active memberships per user, effective access = union of
approved memberships; manager scope is flexible (department or team); engineer
scope is team; client scope is project; admin/exec are global.

Decide:
- The `memberships` table shape: `user_id`, `role`, `scope_type`
  (`global|department|team|project`), `scope_id` (nullable), `status`
  (`pending|approved|revoked`), `approved_by`, timestamps — or an alternative.
- Whether `users.role` survives, is dropped, or is deprecated-but-kept.
- How effective roles and the allowed project scope are derived for read
  endpoints.

## Answer

Decided:

- **One `memberships` table is the sole source of role + scope.** Columns:
  `id`, `user_id` (FK → users), `role` (`admin|exec|manager|engineer|client`),
  `scope_type` (`global|department|team|project`), `scope_id` (nullable),
  `status` (`pending|approved|revoked`), `requested_by`, `approved_by`,
  `reason`, `created_at`, `decided_at`.
- **Scope pointer is polymorphic**: `scope_type` + `scope_id` (String(32),
  app-validated, no DB FK) — dangling ids are possible if an entity is deleted,
  accepted for simplicity. `admin`/`exec` are `scope_type='global'` with
  `scope_id NULL`; `manager` → `department|team`; `engineer` → `team`;
  `client` → `project`.
- **`users.role` is dropped** after the backfill into memberships (ticket 07
  owns the migration; ticket 06 rewrites the gates that read it).
- **Duplicate active grants are blocked at the DB**: partial unique index on
  `(user_id, role, scope_type, scope_id)` where `status='approved'`.
- **Effective access = union of approved memberships**: `global` → all
  projects; `department` → all its teams' projects; `team` → its projects;
  `project` → that one. Ticket 06 owns deriving and enforcing this.

Refined by 05: the pending state lives in the `requests` table; memberships are
only created on approval, so `memberships.status` is `approved|revoked` (the
`pending` value is dropped). Multiple managers may hold memberships on the same
department; one manager may hold memberships over several teams or the whole
department.