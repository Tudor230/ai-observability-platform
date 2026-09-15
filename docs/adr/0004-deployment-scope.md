# ADR-0004: Docker Compose is the supported deployment for the prototype

Status: Accepted

## Context

docs/04 §4.7/§4.8 describe a Kubernetes deployment (ingress, managed Postgres,
probes, scaling). The implementation ships a single Docker Compose stack
(Postgres + Phoenix + backend + dashboard) with a shared database instance
(ADR-0002). Reviewers asked whether the K8s requirement is met or explicitly
descoped.

## Decision

- **Docker Compose is the supported deployment for this prototype.** The stack
  runs with `docker compose up -d --build`, publishes the dashboard, API and
  Phoenix UI, persists Postgres in a named volume (`pgdata`), restarts services
  unless stopped, and pins the Phoenix image by digest for reproducibility.
- **Kubernetes manifests are deferred to production.** The migration path is:
  managed Postgres (or a Postgres StatefulSet) replacing the compose `postgres`
  service; `backend`/`frontend`/`phoenix` as Deployments behind an Ingress with
  TLS; secrets via `Secret` objects (`AIOBS_ADMIN_API_KEY`, `AIOBS_READ_API_KEY`,
  database URL); readiness probes on `/health` and Phoenix `/health`; a
  `Job`/initContainer running `alembic upgrade head` before rollout; HPA on the
  API; periodic `POST /maintenance/purge` or a CronJob for retention
  (ADR-0003).

## Consequences

- The project is honest about scope: no untested YAML pretending to be a
  production deployment exists in the repo.
- Production hardening gaps are explicit (no TLS termination, no orchestrator
  health management, single-node Postgres, default demo secrets unless
  overridden by env).
- CI continues to validate the compose-based path that is actually shipped.

## Alternatives considered

- **Shipping minimal K8s manifests untested**: rejected; untested manifests
  drift and mislead.
- **Moving to a managed service (e.g. a hosted Postgres + Phoenix)**: out of
  scope for the evaluation environment.
