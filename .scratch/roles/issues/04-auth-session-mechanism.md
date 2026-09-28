# 04 — Auth & session mechanism

Type: grilling
Status: resolved

## Question

How do users authenticate?

Settled constraints (from charting): email/password + JWT httpOnly cookie;
admin-provisioned accounts only (no public signup); bootstrap admin seed.

Decide:
- JWT payload claims + TTL; cookie flags (`httpOnly`, `secure`, `samesite`).
- Secret config (`AIOBS_JWT_SECRET`), incl. fail-fast when unset in prod.
- Password hashing library/algorithm.
- Endpoint shapes for `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`.
- The admin-key endpoint that mints password accounts (extends `users.py`).
- Coexistence with existing user API keys (`users.api_key_hash`, `x-api-key`)
  for CLI/SDK reads.

## Answer

Decided:

- **Libraries**: add `PyJWT` (HS256) + `bcrypt` (password hashing). PyPI is
  reachable from this environment.
- **Token**: claims `sub` (user id), `ver` (token version), `iat`, `exp`.
  Roles are **not** embedded — they are derived from memberships per request.
  TTL **24h sliding**: `/auth/me` re-issues the cookie on use.
- **Revocation**: every request loads the user and checks `enabled`; a new
  `users.token_version` is bumped on password change so old tokens die.
- **Cookie/CSRF**: `httpOnly` always; `Secure` configurable (on in prod, off
  for localhost); `SameSite=Lax`; mutating endpoints require a custom header;
  CORS tightened from `*` to configured origins.
- **Endpoints**: `POST /auth/login` (email+password → Set-Cookie + profile),
  `POST /auth/logout` (clears cookie), `GET /auth/me` (user + memberships +
  effective access; slides the cookie).
- **Provisioning/coexistence**: extend admin-only `POST /users` with an
  optional `password` (auto-generated and returned once if omitted); keep
  minting user API keys. Both methods coexist: password session for the
  browser, user API key for CLI/automation. Project ingest keys continue to
  auto-attribute workflow runs to a project, and the project→team→department
  hierarchy supplies the rollup (see map fog for keys scoped above project
  level).
- **Secret**: `AIOBS_JWT_SECRET` is required — the app refuses to start
  without it; docker-compose, README, and the test env get updated.