# Roles & Registration Plan (v1)

Membership-based RBAC and self-service registration for the **Agentic
Observability and FinOps Platform**, derived from the wayfinder map in
[`.scratch/roles/`](../.scratch/roles/map.md) (10 resolved decision tickets,
research in `.scratch/roles/research/`, UI prototypes in
`.scratch/roles/prototypes/`). Replaces the flat, opt-in RBAC (free-form
`users.role` + frontend persona switcher) with real org-scoped roles.

## 1. Purpose

Answer **who can see and do what** across the org hierarchy, and let teams
self-register:

> Department → Team → Project; people hold **memberships** (role + scope);
> creating org units or joining one is a **request** approved by a manager who
> covers the scope; login is email/password; reads are scoped to what your
> memberships allow.

## 2. Scope

**In scope**

- `Department` entity; `Team` gains `department_id`; projects unchanged.
- `memberships` (role + scope + status) as the single source of truth for
  authorization; `users.role` dropped.
- `requests` + approval workflow (entity creation and membership changes),
  with scope-covering-manager approval.
- Email/password auth: PyJWT HS256 in an httpOnly cookie, 24h sliding,
  `token_version` revocation; admin-provisioned accounts.
- `require_access(*roles)` dependency deriving allowed projects from
  memberships; team-scoped reads across all read routers.
- Frontend: login, user menu, union nav, Requests page, Project page, dedicated
  Client view; persona switcher removed.
- One destructive Alembic revision (see §7).

**Out of scope** (see §13): SSO/OAuth/2FA, client share-links,
alert-acknowledgement workflows, approval notifications, membership lifecycle
(revocation/reassignment/rename), org-level ingest keys.

## 3. Data model

All models live in `backend/src/aiobs_backend/models.py`.

### 3.1 New tables

| Table | Columns |
|---|---|
| `departments` | `id` (String(32) uuid), `name` (String(120), unique), `created_at` |
| `memberships` | `id`, `user_id` FK→users, `role` (`admin\|exec\|manager\|engineer\|client`), `scope_type` (`global\|department\|team\|project`), `scope_id` (String(32), nullable), `status` (`approved\|revoked`), `requested_by`, `approved_by`, `created_at`, `decided_at` |
| `requests` | `id`, `type` (`create_department\|create_team\|create_project\|membership`), `requester_id` FK→users, `payload` JSONB, `status` (`pending\|approved\|rejected\|cancelled`), `approver_id`, `reason`, `created_at`, `decided_at` |

- Scope pointer is **polymorphic** (`scope_type` + `scope_id`, app-validated,
  no DB FK).
- Partial unique index on `(user_id, role, scope_type, scope_id)` where
  `status='approved'` — one active grant per scope
  (`.scratch/roles/issues/03-membership-data-model.md`).
- Indexes: `memberships(user_id)`, `memberships(scope_type, scope_id)`,
  `requests(status)`, `requests(requester_id)`.

### 3.2 Changed tables

- `teams` + `department_id` FK→departments (not null after migration).
- `users` + `password_hash` (nullable until set), + `token_version` (int,
  default 0); **drop `role`**.
- `projects` unchanged (`team_id` FK already present).

### 3.3 Role → scope matrix

| Role | Scope | Sees |
|---|---|---|
| `admin` | global | everything |
| `exec` | global | business + shared views, all projects |
| `manager` | department or team (flexible) | covered projects, traces + business |
| `engineer` | team | covered projects, traces |
| `client` | project | own projects, read-only, cost-free |

Multiple active memberships per user; effective access = **union**
(`.scratch/roles/issues/03-membership-data-model.md`).

## 4. Auth & sessions

`.scratch/roles/issues/04-auth-session-mechanism.md`.

### 4.1 Libraries & config

- Dependencies: `PyJWT` + `bcrypt` (add to `backend/pyproject.toml`).
- `config.py`: `jwt_secret: str` (required — fail fast at startup),
  `jwt_ttl_s: int = 86400`; `admin_email`/`admin_password` optional bootstrap.
- `security.py`: `hash_password`/`verify_password` (bcrypt),
  `create_token`/`decode_token` (PyJWT HS256, claims `sub`, `ver`, `iat`,
  `exp`).

### 4.2 Routes (`backend/src/aiobs_backend/api/routes/auth.py`)

| Route | Behavior |
|---|---|
| `POST /api/v1/auth/login` | email+password → `Set-Cookie` (httpOnly, SameSite=Lax, Secure per config), returns profile |
| `POST /api/v1/auth/logout` | clears the cookie |
| `GET /api/v1/auth/me` | user + memberships + effective roles; re-issues the cookie (sliding TTL) |

Cookie: httpOnly always, `Secure` configurable (on in prod), `SameSite=Lax`.
Mutating endpoints require a custom CSRF header. CORS tightened from `*` to
configured origins.

### 4.3 Dependencies (`backend/src/aiobs_backend/api/deps.py`)

- `get_current_user` — reads the JWT cookie; rejects disabled users; checks
  `ver == user.token_version`.
- `require_access(*roles)` — resolves the caller via **session cookie or user
  API key** (`x-api-key`), derives the allowed-project set, checks the role,
  and yields scope for routers. Admin key and service read key bypass scoping.
- `get_admin_key` → dual auth: `x-admin-key` **or** an admin session.
- `require_read_access` (dead) is removed.

### 4.4 Bootstrap & coexistence

- Optional idempotent seed at startup: `AIOBS_ADMIN_EMAIL` +
  `AIOBS_ADMIN_PASSWORD` → user + global `admin` membership.
- Admin `POST /api/v1/users` gains an optional `password` (auto-generated and
  returned once if omitted); user API keys keep being minted.
- Project ingest auth (`x-project-name` + `Bearer <project key>`) is untouched.

## 5. Requests & approvals

`.scratch/roles/issues/05-request-approval-semantics.md`.

### 5.1 Types & payloads

| Type | Payload | Approver |
|---|---|---|
| `create_department` | `{name}` — requester becomes initial manager | admin/exec |
| `create_team` | `{name, department_id}` | managers covering the department |
| `create_project` | `{project_id, name, team_id}` | managers covering the team or its department |
| `membership` | `{role, scope_type, scope_id}` | managers covering the scope; **manager grants → admin/exec only** |

### 5.2 Lifecycle

`pending → approved | rejected`; requester may **cancel**; at most one pending
per `(requester, type, payload)`; rejected requests can be resubmitted;
approval re-checks uniqueness and fails cleanly; **rejection reason required**.

### 5.3 Materialization on approval

- Department → create `departments` row + approved **department-scoped
  manager** membership for the requester.
- Team → create `teams` row (no manager nomination; the department manager
  covers it).
- Project → create `projects` row **without a key**; any engineer/manager
  member can mint/rotate later (clients cannot).
- Membership → create the approved `memberships` row.

### 5.4 API surface (`routes/requests.py`)

`POST /requests`, `GET /requests` (mine + those I can approve),
`POST /requests/{id}/approve`, `POST /requests/{id}/reject`,
`POST /requests/{id}/cancel`.

## 6. Scoped reads

`.scratch/roles/issues/06-scoped-read-enforcement.md`, research in
`.scratch/roles/research/01-backend-read-surface.md`.

### 6.1 Derivation

Allowed projects = union over approved memberships: `global` → all;
`department` → all its teams' projects; `team` → its projects; `project` → that
one. Computed per request in `require_access`.

### 6.2 Role → endpoint map

| Endpoint(s) | Roles |
|---|---|
| `executions`, `executions/{id}` (+spans/failures), `agents` | engineer, manager, client (scoped) |
| `workflows` | engineer, manager, client (scoped), exec (global) |
| `costs`, `clients`, `budgets/status` | manager (scoped), exec (global) |
| `overview`, `metrics`, `alerts` | all authenticated (scoped) |
| admin endpoints (projects/users/pricing/budgets CRUD/maintenance) | admin key or admin session |

### 6.3 Interactions

- `project_id` query param and `x-project-name` are intersected with the
  allowed set; an out-of-scope requested project → **404**; lists filtered
  silently.
- Alerts and `budgets/status` become scoped by the allowed set; global/total
  rows only for exec/admin.
- **Client cost stripping**: the backend omits cost fields from shared payloads
  for the `client` role (data minimization, not UI-only hiding).
- New non-admin scoped `GET /projects` (plus `GET /departments`,
  `GET /teams`) in a new `routes/directory.py`, feeding the frontend filter and
  forms.
- `POST /projects/{id}/rotate` becomes member-authorized (coverage check)
  instead of admin-only; disable/enable stay admin.
- Removed: implicit demo open-reads when `AIOBS_READ_API_KEY` is unset, and the
  dead `require_read_access`.

## 7. Migration (destructive reset)

`.scratch/roles/issues/07-migration-backcompat.md`. One revision, revising
`a445f80da69f`.

1. **Drop data** (FK-safe order): `alerts`, `budgets`, `daily_metrics`,
   `cost_records`, `spans`, `executions`, `workflows`, `agents`, `clients`,
   `projects`, `teams`, `users`. **Pricing is kept.**
2. **Schema**: create `departments`, `memberships`, `requests`; add
   `teams.department_id`; alter `users` (+`password_hash`, +`token_version`,
   −`role`).
3. **No backfill** — legacy teams/users are gone; the org tree starts empty and
   is built through the request flow.
4. `seed.py`: `seed_demo_project` creates a department + team; bootstrap admin
   seeded from env (§4.4).

Downgrade recreates `users.role` and drops the new tables (data loss is
irreversible and accepted).

## 8. Frontend

`.scratch/roles/issues/08-frontend-auth-session-swap.md`,
`.scratch/roles/issues/09-registration-approvals-ux.md`,
`.scratch/roles/issues/10-client-role-view.md`, research in
`.scratch/roles/research/02-frontend-role-surface.md`.

### 8.1 API client (`src/api/client.ts`)

One fetch wrapper sends `credentials` and the CSRF header on mutations; a
global 401 handler clears auth state and redirects to `/login`; add
`post`/`patch` methods. Query cache cleared on login/logout.

### 8.2 Auth state

`src/state/AuthContext.tsx` replaces `RoleContext.tsx`; session from
`GET /auth/me`. New `src/pages/Login.tsx` (full-page, outside the shell) with
return-to redirect; a splash while `/auth/me` loads. TopNav **user menu**
(email + logout) replaces `RoleSwitcher`.

### 8.3 Routes & nav

`RequireAuth` wrapper; nav = union of permitted views (`AppShell.NAV_ITEMS`).

| Route | Roles |
|---|---|
| `/` Overview | all authenticated |
| `/engineering`, `/engineering/:id` | engineer, manager |
| `/manager` | manager, exec |
| `/executive` | exec |
| `/client` | client |
| `/requests` | all authenticated (Approvals badge when the user covers pending requests) |
| `/projects/:id` | members of the project (mint key) |
| `/login` | anonymous |

### 8.4 Requests page (`src/pages/Requests.tsx`)

Three tabs: New request / Approvals / My requests. Request forms with a type
picker; membership form is **role-first** (scope options filter by role). One-
click approve; **reject via a modal with a required reason** (new dialog
primitive in `src/components/core/`). My requests supports cancel, resubmit,
and "Open project".

### 8.5 Client view & project page

`src/pages/Client.tsx`: KPI tiles, executions/errors trend, workflow list with
failure-kind drill-down, recent executions (failure tree, no spans/prompts), and
scoped alerts — no costs. `src/pages/Project.tsx`: project identity + **Mint
API key** (plaintext once).

### 8.6 Removals

`RoleContext.tsx`, `RoleSwitcher`, the `aiobs.role` localStorage key, and the
persona-based `RequireRole` allowances.

## 9. Implementation phases

| Phase | Scope | Depends on |
|---|---|---|
| **1 — Model & auth** | §3 tables/models, §7 migration, §4 auth endpoints/deps/config, bootstrap seed, Python deps | — |
| **2 — Requests** | §5 requests/approvals routes + materialization, dual admin auth, user password provisioning | 1 |
| **3 — Scoped reads** | §6 `require_access`, router rewrites, alerts/budgets scoping, client cost stripping, scoped `directory` routes, rotate re-auth | 1, 2 |
| **4 — Frontend auth** | §8.1–8.3 client wrapper, `AuthContext`, login, nav/route map | 1 |
| **5 — Frontend features** | §8.4 Requests page + dialog, §8.5 client/project pages, filter from `GET /projects` | 3, 4 |
| **6 — Verify & document** | §10 tests, compose/README/env updates, remove dead paths | 1–5 |

## 10. Testing & verification

**Backend** (`backend/tests/`; schema built via `create_all`, so the migration
is not exercised by the suite):

- New: `test_auth.py` (login/logout/me, TTL/`token_version`, disabled user,
  CSRF/secure flags), `test_requests.py` (submit/approve/reject/cancel,
  approver resolution, materialization, dedupe), `test_scope.py` (union access,
  404 out-of-scope, client cost stripping).
- Rework: `test_rbac.py`, `test_read_access.py`, `tests/conftest.py` seeds;
  `scripts/e2e_smoke.py` updated for login + scoped reads.
- Gates: `uv run ruff check`, `uv run mypy`, full pytest.

**Frontend** (`frontend/`): `npm run test` (Vitest), `npm run build`,
`npm run lint`; manual flows — login → submit request → approve → scoped views
→ client view → project key mint.

## 11. Config & deployment changes

| Item | Change |
|---|---|
| `AIOBS_JWT_SECRET` | **new, required** — backend refuses to start without it |
| `AIOBS_ADMIN_EMAIL` / `AIOBS_ADMIN_PASSWORD` | new, optional bootstrap admin |
| `AIOBS_READ_API_KEY` | stays as the service read key (scoping bypass); implicit demo open-reads removed |
| `docker-compose.yml` | add the three env vars (dev defaults for admin) |
| `backend/README.md` | document auth, scoping, bootstrap admin, new env table rows |
| `README.md` | quickstart: login credentials + how to mint the demo project key |

## 12. Deferred / not yet specified

- Approval notifications (email/webhook) and request editing UX.
- Membership lifecycle: revocation, manager reassignment, dept/team rename.
- SDK ingest keys scoped above project level (team/department keys).
- Admin combined "all views" dashboard.

## 13. Out of scope

- SSO/OAuth/2FA.
- Client share-link access (client = per-project membership only).
- Alert-acknowledgement workflows.

## 14. Decision index

- [`01 — Backend read-surface enumeration`](../.scratch/roles/issues/01-backend-read-surface.md) ·
  [research](../.scratch/roles/research/01-backend-read-surface.md)
- [`02 — Frontend role-surface enumeration`](../.scratch/roles/issues/02-frontend-role-surface.md) ·
  [research](../.scratch/roles/research/02-frontend-role-surface.md)
- [`03 — Membership data model`](../.scratch/roles/issues/03-membership-data-model.md)
- [`04 — Auth & session mechanism`](../.scratch/roles/issues/04-auth-session-mechanism.md)
- [`05 — Request & approval semantics`](../.scratch/roles/issues/05-request-approval-semantics.md)
- [`06 — Scoped read enforcement`](../.scratch/roles/issues/06-scoped-read-enforcement.md)
- [`07 — Migration & back-compat`](../.scratch/roles/issues/07-migration-backcompat.md)
- [`08 — Frontend auth/session swap`](../.scratch/roles/issues/08-frontend-auth-session-swap.md)
- [`09 — Registration & approvals UX`](../.scratch/roles/issues/09-registration-approvals-ux.md) ·
  [prototype](../.scratch/roles/prototypes/09-registration-approvals.html)
- [`10 — Client role view`](../.scratch/roles/issues/10-client-role-view.md) ·
  [prototype](../.scratch/roles/prototypes/10-client-view.html)
- [`docs/adr/0006-membership-rbac-jwt-sessions.md`](../docs/adr/0006-membership-rbac-jwt-sessions.md)
