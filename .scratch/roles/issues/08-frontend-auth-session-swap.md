# 08 — Frontend auth/session swap

Type: grilling
Status: resolved
Blocked by: 02, 04

## Question

How does the frontend move from persona switcher to real auth?

Settled constraints (from charting): real login replaces the persona switcher;
reads are authenticated-only per 06, so unauthenticated visitors must be
redirected to login rather than shown empty dashboards.

Decide:
- `AuthContext` replacing `RoleContext`, session driven by `GET /auth/me` (see
  02 for every touchpoint, 04 for the API).
- Login page + redirect-when-unsigned-in.
- Cookie handling through the Vite dev proxy and prod nginx (`credentials`,
  same-origin, CSRF).
- Route/nav gating from real roles, incl. the new `client` role.
- What replaces `RoleSwitcher`.

## Answer

Decided:

- **No persona switcher.** Nav shows the union of views the user's roles
  permit; route guards accept any permitted role; admin implicitly gets
  everything. `RoleContext`, `aiobs.role`, `RoleSwitcher` are removed.
- **`AuthContext`** drives session state from `GET /auth/me`; roles are the
  effective roles from the caller's memberships.
- **Route/nav map**: `/` Overview → all authenticated; `/engineering`,
  `/engineering/:id` → engineer, manager; `/manager` → manager, exec;
  `/executive` → exec; `/client` → client (shaped by ticket 10) + Overview.
- **Login/session UX**: full-page `/login` outside the shell; unauthenticated →
  redirect with return-to; a splash while `/auth/me` loads avoids redirect
  flash; TopNav user menu (email + logout) replaces the switcher.
- **Project filter source**: a new **non-admin, scoped `GET /projects`**
  returns the caller's allowed projects (id + name) for the FilterToolbar (a
  read-surface addition to ticket 06).
- **API layer**: one fetch wrapper sends credentials + the CSRF custom header
  on mutations; a global 401 handler clears auth state and redirects to
  `/login`; the query cache is cleared on login/logout.

Added by 09: a single `Requests` nav item for all authenticated users
(approvals badge for users who cover pending requests).