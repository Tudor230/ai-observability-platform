# Roles & Registration Planning Map

## Destination

Roles built end-to-end into the platform: **Department → Team → Project**
hierarchy; membership-based roles (**admin**/exec global, **manager**
dept-or-team, **engineer** team, **client** project); self-service
registration + membership requests approved by managers (the department creator
becomes its initial manager; manager grants by admin/exec); **email/password
login with JWT cookie sessions**; **team-scoped reads** enforced across backend
and frontend. Map complete when every ticket below is `resolved` and the
persona switcher is gone.

## Notes

- Domain: AI observability / FinOps. Use the `CONTEXT.md` glossary terms
  (execution, failure kind, attribution dimensions); `docs/06` flags the
  multi-tenancy trap (project-scoped reads are the known weak spot).
- Skills to consult when resolving: **grilling** + domain-modeling (default);
  **prototype** for 09/10; **research** for 01/02 (already resolved at chart
  time).
- Settled before charting — do not re-open:
  - Hierarchy: Department → Team → Project.
  - Roles: engineer, manager, exec, client + admin (`sdm`→manager,
    `finance`→exec).
  - Entity creation AND membership changes both route through manager approval.
  - Any authenticated user can submit a request (self-service).
  - Email/password + JWT httpOnly cookie; admin-provisioned accounts only;
    bootstrap admin seed; no public signup.
  - Team-scoped reads: engineer/manager → their team's projects; exec/admin →
    all; client → own projects.
  - Manager = flexible assignment (dept or team); multiple active memberships
    per user; effective access = union of approved memberships.
  - Manager assignments are admin/exec-approved; **the requester who creates a
    department becomes its initial manager** (department-scoped). Several
    managers may share a department, each covering one or several teams.
  - Client = distinct role string with a custom minimal read-only view.
- Back-compat surface to respect: `users.role` (`admin|engineer|sdm|finance`)
  + `require_role()` gates in `api/deps.py`; admin-key endpoints (`users.py`,
  `projects.py`); ingest auth (`x-project-name` + Bearer) must not break;
  frontend persona `RoleContext`/`RoleSwitcher`.

## Decisions so far

- [01 — Backend read-surface enumeration](issues/01-backend-read-surface.md):
  every read endpoint, its role gate, and its scope handling enumerated (see
  research/01-backend-read-surface.md).
- [02 — Frontend role-surface enumeration](issues/02-frontend-role-surface.md):
  every persona-role touchpoint enumerated (see
  research/02-frontend-role-surface.md).
- [03 — Membership data model](issues/03-membership-data-model.md): one
  `memberships` table is the sole source of role+scope (polymorphic
  `scope_type`+`scope_id`, no FK); `users.role` dropped; partial unique index
  blocks duplicate active grants; effective access = union of approved
  memberships.
- [04 — Auth & session mechanism](issues/04-auth-session-mechanism.md): PyJWT
  (HS256) + bcrypt; 24h sliding httpOnly `SameSite=Lax` cookie with custom
  header on mutations + tightened CORS; `sub`/`ver`/`exp` claims, roles derived
  per request, `token_version` revocation; `/auth/login|logout|me`; admin
  `POST /users` gains optional password while user API keys survive;
  `AIOBS_JWT_SECRET` required (fail fast).
- [05 — Request & approval semantics](issues/05-request-approval-semantics.md):
  one `requests` table (type + JSONB payload) holds all pending state; approval
  materializes entities/memberships; approvers are scope-covering managers
  (admin/exec for departments and manager grants); per-requester dedupe, cancel,
  required rejection reason; project keys minted post-approval by any member.
- [06 — Scoped read enforcement](issues/06-scoped-read-enforcement.md):
  `require_access(*roles)` resolves the caller and derives allowed projects from
  approved memberships; requests intersect with the shared dependency, lists
  filtered, out-of-scope → 404; exec keeps business+shared but not trace detail;
  client gets shared+traces, no costs; alerts/budgets scoped by the allowed set;
  authenticated reads only (demo open-reads removed, `require_read_access`
  dropped).
- [07 — Migration & back-compat](issues/07-migration-backcompat.md): one
  destructive alembic revision — drops all trace-derived data and users (no
  backfill), creates the new tables, keeps pricing, dual auth for admin
  endpoints (admin key or admin session), optional env bootstrap-admin seed.
- [08 — Frontend auth/session swap](issues/08-frontend-auth-session-swap.md):
  no persona switcher — nav is the union of permitted views; `AuthContext` from
  `/auth/me`; full-page `/login` with return-to + TopNav user menu; route map
  (`/engineering` eng+mgr, `/manager` mgr+exec, `/executive` exec, `/client`
  client); new scoped `GET /projects` feeds the filter; central fetch wrapper
  with CSRF header and global 401 → `/login`.
- [09 — Registration & approvals UX](issues/09-registration-approvals-ux.md):
  one `Requests` page (New request / Approvals / My requests) + nav item with
  badge; role-first membership form; one-click approve, reject via
  required-reason modal; project keys minted on a project page. Prototype:
  [prototypes/09-registration-approvals.html](prototypes/09-registration-approvals.html).
- [10 — Client role view](issues/10-client-role-view.md): dedicated `/client`
  dashboard (KPIs, executions/errors trend, workflows + failure-kind
  drill-down, recent executions, scoped alerts) plus the shared Overview with
  cost fields stripped server-side; failure tree allowed, no raw spans/prompts;
  no key minting. Prototype:
  [prototypes/10-client-view.html](prototypes/10-client-view.html).

## Fog / not yet specified

- Approval notifications (email/webhook) + request re-submission/editing UX.
- Membership lifecycle: revocation, manager reassignment, dept/team rename.
- Whether SDK ingest keys can be scoped above project level (team/department
  keys auto-assigning runs to a project within that scope) — today ingest is
  project-keyed.
- Whether admin keeps a combined "all views" dashboard.

## Out of scope

- SSO/OAuth/2FA — not requested.
- Client share-link access — ruled out (client = per-project membership only).
- Alert-acknowledgement workflows — existing backend fog, a separate effort.