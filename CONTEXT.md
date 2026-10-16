# Domain Context

One context: the **Agentic Observability and FinOps Platform**. Vision in
`docs/01`–`docs/05`; plans in `plans/`; implementation in `sdk/`, `backend/`,
`frontend/`. Decisions recorded in `docs/adr/` and `.scratch/*/issues/`.

## Glossary (use exactly these terms)

- **Trace** — a single end-to-end agentic execution, identified by `trace_id`.
- **Span** — one step in a trace (LLM call, tool call, retrieval, agent step,
  workflow step). Carries an OpenInference `openinference.span.kind`
  (`LLM`/`TOOL`/`RETRIEVER`/`AGENT`/`CHAIN`/…).
- **Workflow root** — the CHAIN span that bounds a business execution; the SDK
  stamps it with `sdk.workflow_id` and `session.id` (= `workflow_id`), and — in
  debug mode only — `sdk.project_id`. Ingest always stores the authenticated
  project's id there (ADR-0008). The backend turns each workflow root into one
  **execution**.
- **Execution** — the backend's normalized record of a workflow root (status,
  cost, tokens, call counts, latency, failure info).
- **Failure kind** — the backend's authoritative classification of a failing
  span: `rate_limit`, `timeout`, `invalid_output`, `tool_error`,
  `provider_error`, `retrieval_error`, `validation_error`, `business_logic`.
  The SDK emits best-effort `sdk.error.kind` hints; the backend owns the
  taxonomy.
- **Cost** — USD computed by the backend cost engine from token counts × pricing
  (exact → prefix → provider-default chain); unpriced models have `NULL` cost.
- **Attribution dimensions** — project, workflow, agent, team; how cost and
  usage roll up. (Client was retired as a dimension — ADR-0011; the `client`
  RBAC role below is a different concept.)
- **Analytics metric** — daily aggregates (executions, error rate, tokens, cost,
  avg/p50/p95/p99 latency) per dimension.
- **Alert / Budget** — budget = configured spend cap per period/dimension;
  alert = an open notification when utilization crosses 80% (warning) / 100%
  (critical).
- **Contract (`aiobs-contracts`)** — shared SDK↔backend definitions (attribute
  names, failure taxonomy, redaction rules, hint patterns); never re-declare
  them in one side.
- **OTLP ingest** — the backend's `POST /v1/traces` (and `/api/v1/traces`)
  receiver that decodes SDK OTLP protobuf and resolves the project from
  `authorization: Bearer <api_key>` (ADR-0008). The `x-project-name` header and
  the root's `sdk.project_id` are debug-only assertions: a conflict is rejected,
  and stored root identity is server-authoritative.
- **Project name** — the unique human handle for a project; the only project
  label any dashboard surface shows (ADR-0012).
- **Generated project id** — `p_<12 hex>`, assigned by the backend at creation
  and never rendered by the dashboard; it stays the technical token in URLs,
  query params, ingest routing and analytics dimension keys (ADR-0012).
- **Client role** — a project-scoped, read-only, cost-free membership role
  (ADR-0006); unrelated to the retired client *dimension*, and untouched by it.
- **Unit cost** — a cost per unit (per 1M tokens, per execution); rendered with
  four decimals because totals-style rounding would flatten it to cents.
- **Model insights** — per provider·model economics from `GET /models`: calls,
  failures, tokens, cost (billing `cost_records`) and avg/p95 latency (LLM
  spans).
- **Tool insights** — per-tool reliability from `GET /tools`: calls, failures,
  error rate and avg/p95 duration of TOOL spans.

## Explicitly avoided synonyms

- Do not say "run/job/transaction" for **execution**.
- Do not say "error type/category" for **failure kind**.
- Do not say "endpoint" for **execution**.
- Do not say "KPI metric" — **KPIs** are `docs/05` success criteria; **metrics**
  are the analytics aggregates.