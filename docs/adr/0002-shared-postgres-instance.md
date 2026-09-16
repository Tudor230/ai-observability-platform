# ADR-0002: One shared Postgres instance for Phoenix, the backend, and SDK tooling

Status: Accepted

## Context

The platform shipped two docker-compose stacks:

- root `docker-compose.yml` — the full platform (Postgres, Phoenix, backend, dashboard);
- `sdk/dev/docker-compose.yml` — a standalone SDK dev stack with its own Postgres + Phoenix.

The SDK's e2e test and `dev/inspect_traces.py` defaulted to the SDK stack's
Postgres, so SDK-visible traces landed in a different instance than the data the
backend uses, and two Phoenix trace stores existed. The platform should have one
Postgres instance associated with the Phoenix/Arize deployment — shared by the
SDK tooling and the backend, on the standard DB port `5432`.

## Decision

- Exactly one Postgres instance, defined by the root `docker-compose.yml` on host
  port `5432` and initialized by `dev/db-init/01-init.sql` with:
  `phoenix` (Phoenix trace storage), `aiobs` (platform data), `aiobs_test`
  (backend test suite).
- Phoenix, the backend, and the SDK tooling/e2e tests all connect to that
  instance. SDK tooling defaults to
  `postgresql://postgres:postgres@localhost:5432/phoenix`; the backend defaults
  to `...@127.0.0.1:5432/aiobs` (`aiobs_test` for tests).
- `sdk/dev/docker-compose.yml` is removed; SDK docs and CI start `postgres` +
  `phoenix` from the root compose (`docker compose up -d --wait postgres phoenix`).
- DSNs stay overridable (`AI_OBSERVABILITY_PG_DSN`, `AIOBS_DATABASE_URL`,
  `AIOBS_TEST_DATABASE_URL`) so an external/managed Postgres can be substituted
  without code changes.

## Consequences

- SDK dev traces, the Phoenix UI, and the platform's analytics always refer to
  the same database instance; one container to run, reset, and back up.
- The SDK e2e tests now require the root stack, and the SDK CI job depends on
  the root compose file (workflow path filter includes `docker-compose.yml` and
  `dev/**`).
- The container binds the standard port `5432`, so a host Postgres already
  listening there must be stopped (or the published port changed via the compose
  mapping) before starting the stack.

## Alternatives considered

- Keep the standalone SDK stack: isolates SDK development but splits traces
  across two instances — the problem this ADR fixes; rejected.
- Share one Docker network between the two stacks: brittle cross-project
  coupling and still two Postgres instances; rejected.
- One database per component on separate instances: rejected — attribution and
  the KPI gate assume a single queryable instance.
