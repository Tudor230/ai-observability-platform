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
  stamps it with `sdk.client_id`, `sdk.project_id`, `sdk.workflow_id` and
  `session.id` (= `workflow_id`). The backend turns each workflow root into one
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
- **Attribution dimensions** — client, project, workflow, agent, team; how cost
  and usage roll up.
- **Analytics metric** — daily aggregates (executions, error rate, tokens, cost,
  avg/p50/p95/p99 latency) per dimension.
- **Alert / Budget** — budget = configured spend cap per period/dimension;
  alert = an open notification when utilization crosses 80% (warning) / 100%
  (critical).
- **Contract (`aiobs-contracts`)** — shared SDK↔backend definitions (attribute
  names, failure taxonomy, redaction rules, hint patterns); never re-declare
  them in one side.
- **OTLP ingest** — the backend's `POST /v1/traces` (and `/api/v1/traces`)
  receiver that decodes SDK OTLP protobuf and validates
  `x-project-name` + `authorization: Bearer <api_key>`.

## Explicitly avoided synonyms

- Do not say "run/job/transaction" for **execution**.
- Do not say "error type/category" for **failure kind**.
- Do not say "endpoint" for **execution**.
- Do not say "KPI metric" — **KPIs** are `docs/05` success criteria; **metrics**
  are the analytics aggregates.