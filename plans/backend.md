# Backend Plan (v1)

Platform backend for the **Agentic Observability and FinOps Platform** (phase 2 of
[`plans/implementation-plan.md`](./implementation-plan.md)). It consumes what the SDK
([`plans/sdk.md`](./sdk.md)) already emits and implements everything the SDK deliberately
defers: authoritative failure classification, cost computation & attribution, analytics,
alerts, project registration/API keys, and the read-side Platform API consumed by the
[dashboard](./frontend.md).

This plan is written against the **actual SDK output contract** (verified in
`sdk/src/ai_observability/`), not against the general vision in `docs/03`–`docs/05`.

## 1. Purpose

Teams register an AI project, get an API key, integrate the SDK, and the backend turns the
SDK's raw telemetry into:

- normalized execution records with business attribution (client / project / workflow /
  agent / team),
- authoritative failure classification (a `failure tree`, not just hints),
- token- and model-derived **cost** attributed across the same dimensions,
- aggregated analytics and alert/budget evaluation,
- a stable read API for the dashboard.

**Product principle (mirrors the SDK):** teams interact with nothing but the SDK and the
dashboard. They never touch Phoenix, Postgres, or the API internals.

## 2. Scope (v1)

- Project registration + API-key issuance and validation.
- Ingest of OTLP HTTP traces (the SDK already speaks OTLP to Phoenix; the backend consumes
  the same trace data).
- Trace normalization + business enrichment into platform entities.
- Authoritative failure classification (taxonomy lives **here**, not in the SDK).
- Cost engine (token counts × pricing, Phoenix-pricing-compatible) + attribution.
- Analytics aggregation (execution / usage / financial metrics).
- Alert + budget engine.
- Platform API (FastAPI) exposing all of the above.
- Containerized deployment alongside Phoenix + Postgres.
- Automated KPI validation against the SDK's mock-workflow harness.

## 3. Architecture & data flow

```text
SDK (LangChain / LlamaIndex)
        |  OTLP HTTP /v1/traces
        |  headers: authorization: Bearer <api_key>, x-project-name: <project_id>
        v
Phoenix (trace ingest + storage; server-side token cost from pricing table)
        |
        v
Backend worker:  trace processing -> failure classification -> cost -> analytics -> alerts
        |
        v
PostgreSQL (platform entities + derived analytics)   <-- dashboard/API read model
        |
        v
FastAPI Platform API (/api/*)
        |
        v
Dashboard (frontend)
```

Two ingestion paths must be reconciled in v1:

1. **Phoenix as the trace store** (as today). The backend either (a) reads spans back out
   of Phoenix/Postgres, or (b) receives a copy of each trace directly from the SDK. Decision
   in [Ticket 02](#decision-index): start with a **direct OTLP receive** into the backend
   (a small OTel collector / FastAPI OTLP endpoint) so the backend owns enrichment and does
   not depend on Phoenix internals; Phoenix remains the canonical trace/UI store. The
   backend is idempotent so both paths can be enabled.

The backend is written in Python (FastAPI), matching the proposed stack in `docs/04 §4.8`.

## 4. Project registration & API keys

The SDK sends `authorization: Bearer <api_key>` and `x-project-name: <project_id>` on every
OTLP export (`sdk/src/ai_observability/_tracing.py`). The backend is the authority for keys.

### 4.1 Entities

- **Team** — owning group for one or more projects.
- **Project** — a registered application that holds an API key + `project_id`
  (stable identifier matching the SDK's `x-project-name` / `sdk.project_id`).
- **APIKey** — `project_id`, secret hash, created/revoked timestamps, optional label.

### 4.2 Key lifecycle

- Admin (or bootstrap) creates a project → generates an API key (random, high-entropy).
- Only a **hash** of the key is stored (e.g. SHA-256); the plaintext is shown once.
- Keys are revoked by disabling; revoked keys reject ingest.

### 4.3 Ingest validation

On each received trace, the backend:

1. Reads `x-project-name` → looks up the project; rejects unknown/disabled projects.
2. Validates `authorization: Bearer <key>` against the project's key hash.
3. Asserts `sdk.project_id` on the root span matches the authenticated project.
4. Rejects malformed/non-OpenInference payloads with a structured error; never crashes the
   ingest path.

## 5. Data model (PostgreSQL)

Platform-specific entities (trace detail stays in Phoenix; see `docs/04 §4.4.8`). All
dollar/token aggregates are stored as `numeric` to avoid float drift in cost.

### 5.1 Dimensions

- `teams` (id, name)
- `projects` (id, team_id, project_id, name, created_at)
- `clients` (id, external_key) — sourced dynamically from `sdk.client_id`; auto-upserted
- `workflows` (id, project_id, name, version, latest_version, first_seen, last_seen)
- `agents` (id, name) — auto-upserted from AGENT spans; agent → workflow via spans

### 5.2 Executions

- `executions` — one row per **workflow root** (identified by a span carrying
  `sdk.workflow_id` / CHAIN root):
  - `trace_id`, `workflow_id` (business key), `session_id` (= workflow_id),
  - `project_id`, `client_id`, `workflow` (name), `workflow_version`,
  - `status` (`ok`/`error`), `root_error_kind`, `started_at`, `ended_at`, `duration_ms`,
  - `metadata` (JSONB, from root `metadata`),
  - `total_cost` (numeric), `input_tokens`, `output_tokens`, `total_tokens`,
  - `llm_calls`, `tool_calls`, `retrieval_calls`, `agent_calls`, `error_count`,
  - `retry_count`.

### 5.3 Spans (normalized)

- `spans` — normalized copy of the SDK spans the backend needs (source of truth remains
  Phoenix):
  - `execution_id`, `trace_id`, `span_id`, `parent_id`, `kind`
    (LLM/CHAIN/AGENT/TOOL/RETRIEVER/EMBEDDING/RERANKER/...),
  - `name`, `status`, `error_type`, `error_message`, `error_kind`, `started_at`,
    `ended_at`, `duration_ms`,
  - `llm_model`, `llm_provider`, `input_tokens`, `output_tokens`, `total_tokens`,
  - `tool_name`, `retrieval_doc_count`, `attributes` (JSONB, raw), `cost` (numeric).

### 5.4 Cost & pricing

- `pricing` — per `provider + model` (+ effective date range, for price changes over time):
  - `input_price_per_1m`, `output_price_per_1m`, `cache_read_price_per_1m`,
    `cache_write_price_per_1m`, `reasoning_price_per_1m`, `currency` (USD v1),
  - seeded from the same table Phoenix uses; editable (custom models supported).
- `cost_records` — one row per billable span: `execution_id`, `span_id`, `provider`,
  `model`, `input_tokens`, `output_tokens`, `price_version`, `amount` (numeric).

### 5.5 Analytics & alerts

- `daily_metrics` / `execution_metrics` — pre-aggregated execution/usage/financial metrics
  (see §8) keyed by dimension + time bucket.
- `budgets` — per project/workflow/client: `amount`, `period`, `period_start`.
- `alerts` — generated alert records: `rule_id`, `severity`, `message`, `triggered_at`,
  `dimension`, `status` (open/acknowledged/closed).

Indexes: `executions(project_id, started_at)`, `executions(workflow_id, started_at)`,
`executions(client_id, started_at)`, `spans(execution_id)`, `cost_records(execution_id)`,
`pricing(provider, model, effective_from)`. Migrations via Alembic.

## 6. Trace processing pipeline

Steps per incoming trace (idempotent — re-processing the same `trace_id` upserts):

1. **Validate** (see §4.3).
2. **Normalize** — flatten SDK/OpenInference attributes into the `spans` table; resolve
   span kinds; rebuild parent/child hierarchy from `trace_id`/`parent_id`.
3. **Identify workflow roots** — a span with `sdk.workflow_id` and
   `openinference.span.kind == CHAIN` (or a CHAIN with no parent). One root ⇒ one
   `executions` row. `session.id` = `workflow_id` (SDK sets both).
4. **Business enrichment** — copy `sdk.client_id`, `sdk.project_id`, `sdk.workflow_id`,
   `sdk.workflow.version`, `user.id`, and parse root `metadata` (JSONB) onto the execution;
   auto-upsert dimension rows (`clients`, `workflows`, `agents`).
5. **Resource extraction** — aggregate LLM/tool/retrieval/agent counts, token totals, and
   latency per execution from child spans.
6. **Hand off** to failure classification (§7) and cost engine (§8) per span, then
   roll up to the execution.

## 7. Failure classification

The SDK emits **best-effort hints** (`sdk.error.kind`: `rate_limit`, `timeout`,
`invalid_output`, `tool_error`, `provider_error`) plus raw material (`sdk.error.type`,
`sdk.error.message`, `exception.*` events, span `status_code`). The backend owns the
**authoritative taxonomy** and may trust, refine, or override the hints.

### 7.1 Taxonomy

| Failure kind | Primary signals |
|---|---|
| `rate_limit` | hint, or `429`/`ratelimit` in type/message |
| `timeout` | hint, or `timeout`/`timed out`/`deadline` |
| `invalid_output` | hint, or JSON/parse/output-parser errors |
| `tool_error` | TOOL span ERROR |
| `provider_error` | LLM span ERROR (provider/model-level) |
| `retrieval_error` | RETRIEVER span ERROR |
| `validation_error` | CHAIN step ERROR w/ validation markers |
| `business_logic` | CHAIN/AGENT ERROR without a lower-layer failure beneath |

### 7.2 Algorithm

- Walk each failing span; classify using kind + span kind + exception material. The hint is
  the starting point; the backend re-checks against raw exception text and span context.
- Build a **failure tree** per execution: each failing span becomes a node (kind, message,
  span id), parented by the span hierarchy.
- **Root propagation**: the execution root's failure is the earliest/deepest root cause,
  consistent with the SDK's propagation (`sdk.error.kind` on root = earliest failure).
- Derive `error_count`, `failed_agents`/`failed_tools`, and per-kind counts.

### 7.3 Retries

The SDK writes `sdk.retry.count`/`sdk.retry.of`. The backend may also **re-derive** retries
from repeated sibling ERROR spans (SDK plan §6.4), storing the max as the authoritative
execution `retry_count`.

## 8. Cost engine

**Phoenix computes cost server-side from token counts + pricing; the backend mirrors the
same model** so the platform owns an auditable, exportable cost record independent of
Phoenix internals. The SDK emits accurate `llm.token_count.prompt/completion` and
`llm.model_name`/`llm.provider` (already normalized/backfilled by the SDK) — the backend
must **not** re-estimate tokens.

### 8.1 Per-LLM-span cost

```text
input_cost  = input_tokens  * input_price_per_1m  / 1_000_000
output_cost = output_tokens * output_price_per_1m / 1_000_000
cost        = input_cost + output_cost
```

Cache-read/write and reasoning-token pricing applied when the pricing row defines them.
Unpriced models → cost `NULL` (visible as "unpriced"), never fabricated.

### 8.2 Attribution

Roll up cost + tokens by the dimensions the UI needs:

- **workflow**, **agent**, **project**, **client**, **team**, and **time** (hour/day/month).

This answers the `docs/03 §3.10` questions (most expensive workflow, cost per client, etc.).

### 8.3 Pricing resolution

- Look up `pricing` by `(provider, model, effective_on = execution date)`.
- Fallback chain: exact model → model-prefix → provider default → unpriced.
- Price changes over time are honored via effective-date ranges (newer executions use
  newer prices); `cost_records` pin the `price_version` used.

## 9. Analytics engine

Pre-aggregate the metrics defined in `docs/03 §3.11` into time-bucketed tables for fast
dashboard reads.

- **Execution metrics**: executions, success/failed, error rate, retry rate, avg latency,
  p50/p95/p99 latency.
- **AI usage metrics**: input/output/total tokens, LLM calls, tool calls, retrieval calls,
  model usage breakdown.
- **Financial metrics**: total cost, avg cost/execution, cost per workflow/agent/client/team.

Computed by a scheduled job (or on-ingest incremental rollups) into `daily_metrics` +
`execution_metrics`. These feed the dashboard's engineering/manager/executive views.

## 10. Alert & budget engine

Evaluate rules on the analytics/execution data (`docs/03 §3.12`):

- cost threshold exceeded (per project/workflow/client),
- token threshold exceeded,
- latency (avg/p95) threshold exceeded,
- error-rate increase,
- excessive tool calls (inefficient execution),
- budget exceeded (against `budgets`),
- unusual consumption vs historical baseline (v1: simple moving-average deviation).

Each rule produces an `alerts` record exposed via the API. Budget utilization is surfaced
as a metric (percent of budget used).

## 11. Platform API (FastAPI)

Stable read-side API for the dashboard (`docs/04 §4.4.9`). Versioned under `/api/v1`.

### 11.1 Resources

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/overview` | top-line KPIs (total cost, executions, error rate, trend) |
| GET | `/api/v1/executions` | paginated/filtered executions (client/project/workflow/status/time) |
| GET | `/api/v1/executions/{id}` | single execution + its span/failure tree |
| GET | `/api/v1/executions/{id}/spans` | normalized spans |
| GET | `/api/v1/workflows` | workflow list + aggregates |
| GET | `/api/v1/workflows/{id}` | workflow detail + per-workflow cost/latency |
| GET | `/api/v1/clients` | client list + cost aggregates |
| GET | `/api/v1/agents` | agent list + aggregates |
| GET | `/api/v1/costs` | cost aggregation by dimension + time range |
| GET | `/api/v1/metrics` | execution/usage/financial metrics (time series) |
| GET | `/api/v1/alerts` | alerts (open/acknowledged/closed), budget status |
| GET/POST/PUT | `/api/v1/pricing` | manage pricing table (admin) |
| GET/POST/PUT | `/api/v1/budgets` | manage budgets (admin) |
| GET/POST | `/api/v1/projects` | manage projects/API keys (admin) |

### 11.2 Conventions

- FastAPI + Pydantic v2 schemas; OpenAPI generated.
- Query params: `client_id`, `project_id`, `workflow_id`, `agent_id`, `status`,
  `start`, `end`, `granularity`, pagination (`limit`/`offset` or cursor).
- Consistent error shape; auth for admin endpoints; read endpoints gated by project scope.
- The dashboard must access **only** these endpoints (no direct DB access) per
  `docs/04 §4.4.9`.

## 12. Phoenix deployment

- Containerized Phoenix + Postgres already defined in `sdk/dev/docker-compose.yml`
  (Phoenix `:6006`, Postgres `:5432`).
- Backend containers join the same compose network (production: the K8s layout in
  `docs/04 §4.7`).
- Phoenix remains the canonical trace store and UI; the backend's normalized `spans` table
  is a platform projection, not a replacement.

## 13. KPI validation (`docs/05`)

Reuse the SDK's deterministic mock-workflow harness to validate the backend:

- **KPI 1 — Observability coverage**: mock scenarios produce known spans/kinds; assert the
  backend reconstructs the expected execution (trace reconstruction, `docs/05 §5.4`).
- **KPI 2 — Cost attribution accuracy**: mock traces carry **fixed** token counts (SDK
  fakes); the cost engine's output is compared to an independently computed expected cost
  for a known pricing row (`docs/05 §5.3`). Cost error must be ~0.
- **Failure classification**: each mock failure scenario (LLM error, tool timeout, invalid
  JSON, retrieval failure, rate limit, retry-then-success) must classify into the expected
  `error_kind` and build the expected failure tree.
- **Alerts**: a scripted abnormal-consumption scenario triggers the expected alert
  (`docs/05 §5.4`).
- These run as a pytest suite against the backend in CI (mirroring `sdk.yml`), plus an
  e2e job against the docker stack.

## 14. Deferred / out of scope (v1)

- Replacing Phoenix's trace storage or cost computation (backend mirrors it).
- Provider-level instrumentor integration beyond the SDK's framework coverage.
- LLM-as-judge / automated evaluation (SDK plan §10).
- Multi-currency beyond USD; per-attempt retry accounting; rate sampling.
- Building the business agents being monitored; model training/fine-tuning.

## 15. Decision index

Resolved during implementation on the wayfinder map `.scratch/backend/` (per
`docs/agents/issue-tracker.md`):

| Ticket | Decision |
|---|---|
| [01 — Ingest path](../.scratch/backend/issues/01-ingest-path.md) | Direct OTLP HTTP receive (`/v1/traces` + `/api/v1/traces`); Phoenix stays the canonical trace store, not a read dependency; idempotent per-trace recompute |
| [02 — Failure taxonomy](../.scratch/backend/issues/02-failure-taxonomy.md) | Authoritative taxonomy in `aiobs_contracts`; trust + refine SDK hints; span-level kinds, execution root carries primary failure |
| [03 — Cost engine](../.scratch/backend/issues/03-cost-engine.md) | Mirror Phoenix pricing; exact → prefix → provider default → unpriced (`NULL`); cache/reasoning tokens priced |
| [04 — Analytics & alerts](../.scratch/backend/issues/04-analytics-alerts.md) | Daily rollup (total/project/client/workflow) with p50/p95/p99; budget-based alert rules; background scheduler + on-demand admin endpoints |
| [05 — API surface](../.scratch/backend/issues/05-api-surface.md) | `/api/v1` reads with optional `x-project-name` scope; admin-key for mutating endpoints; SDK-header auth for ingest |
| [06 — Shared contracts](../.scratch/backend/issues/06-shared-contracts.md) | `shared/aiobs_contracts` as the SDK↔backend single source of truth |

Also recorded as [ADR-0001](../docs/adr/0001-backend-ingest-otlp-direct.md).
