# Backend Planning Map

## Destination

`plans/backend.md` (detailed backend plan) implemented in `backend/` and the
platform backend consumed by the dashboard. Decision tickets below record the
resolved engineering decisions made during implementation.

## Notes

- Domain: AI observability / FinOps. Read `docs/01`–`docs/05` and `plans/sdk.md`
  first — the SDK output contract is the backend's input contract.
- Settled before charting: FastAPI + SQLAlchemy + PostgreSQL; backend holds the
  authoritative failure taxonomy and cost engine; SDK emits raw material only.
- Map complete when every ticket below is `resolved` and the backend passes the
  KPI gate (`backend/scripts/kpi_gate.py`).

## Decisions so far

- [01 — Ingest path](issues/01-ingest-path.md): backend owns a direct OTLP HTTP
  receiver (`POST /v1/traces` + `/api/v1/traces`); Phoenix remains the canonical
  trace store but is not a read dependency. Idempotent per-trace recompute.
- [02 — Failure taxonomy](issues/02-failure-taxonomy.md): authoritative taxonomy
  lives in `aiobs_contracts`; backend trusts SDK `sdk.error.kind` hints but
  refines them from raw exception text (rate limit/timeout/invalid output/
  validation beat generic layer kinds). Span-level kinds; execution root carries
  the primary (earliest) failure.
- [03 — Cost engine](issues/03-cost-engine.md): mirrors Phoenix pricing;
  resolution chain exact → prefix → provider default → unpriced (`NULL`, never
  0); cache-read/write and reasoning token pricing parsed from
  `llm.token_count.prompt_details.*`.
- [04 — Analytics & alerts](issues/04-analytics-alerts.md): daily rollup across
  total/project/client/workflow dimensions with p50/p95/p99 latency; alert rules
  derived from budgets (warn ≥80%, critical ≥100%); background scheduler in the
  app lifespan plus on-demand admin endpoints.
- [05 — API surface](issues/05-api-surface.md): `/api/v1` read endpoints with
  optional `x-project-name` project-scope header; admin-key protected mutating
  endpoints (pricing, budgets, projects, maintenance); ingest auth via
  `x-project-name` + `authorization: Bearer`.
- [06 — Shared contracts](issues/06-shared-contracts.md): attribute names,
  error taxonomy, redaction rules, and hint patterns extracted to a shared
  `aiobs_contracts` package consumed by both the SDK and the backend (no drift).

## Fog / not yet specified

- Multi-tenant RBAC beyond project-scope header; per-user alert acknowledgement
  workflows; pricing history UI; K8s manifests for production deployment.