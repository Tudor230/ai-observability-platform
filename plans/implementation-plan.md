# Implementation Plan (rough)

Rough, platform-wide plan for the **Agentic Observability and FinOps Platform**, assembled from `docs/01`–`docs/05` (the general idea) and the decisions resolved on the SDK map (`.scratch/sdk/`). The detailed SDK plan lives in [`plans/sdk.md`](./sdk.md); backend and frontend plans will sit alongside this file.

## 1. Vision

A centralized platform where teams register AI projects, integrate a simple SDK, and automatically get answers to:

> **What happened in my AI system, how much did it cost, and why did it fail?**

The platform observes agentic applications without owning their business logic: LLM calls, prompts/responses, latency, token usage, costs, tool calls, workflow steps, agent decisions, errors, and retries — grouped into hierarchical traces (`workflow → agent → LLM/tool/retrieval`).

## 2. Problem (from `docs/01`–`docs/02`)

- Teams run agentic applications on different frameworks with no common observability or FinOps layer.
- No cost visibility (tokens ≠ cost until pricing is applied), no business attribution (which client/workflow/project produced a trace), no historical analysis, no anomaly detection, no cross-team comparison.

## 3. Target users (from `docs/01`)

- **Engineers**: execution traces, LLM/tool calls, errors, latency.
- **Managers (SDM)**: cost per workflow/client, consumption trends, budget utilization, agent efficiency.
- **Finance/executives**: total AI cost, cost per client/service, unit economics, forecasts.

## 4. Architecture (from `docs/04`, confirmed by SDK research)

```text
Agentic applications (LangChain / LlamaIndex / ...)
        |   SDK (plans/sdk.md)
        v
OpenTelemetry / OpenInference  →  OTLP HTTP
        v
Phoenix (trace ingest & storage; server-side cost from token counts + pricing)
        v
Platform backend (trace processing, failure classification, analytics, alerts)
        v
PostgreSQL (platform data)  →  Platform API  →  Dashboard
```

Key facts locked by research (`.scratch/sdk/research/01-openinference-coverage.md`):

- **Phoenix** stores spans as-is, computes token counts and **cost server-side** (token counts + model pricing table; ignores externally supplied span costs). It does **not** classify failures — that's the platform backend's job.
- **OpenInference** conventions cover payloads, identity, tokens, and cost attributes, but define **no failure/retry attributes** — the SDK emits its own namespaced attributes (`sdk.error.*`, `sdk.retry.*`) and the backend consumes them.

## 5. Components

| Component | Status | Owner |
|---|---|---|
| **SDK** (Python; config, trace model, failure/usage capture, LangChain+LlamaIndex instrumentation, export reliability, mock workflows) | **Implemented** | `plans/sdk.md` → `sdk/` |
| **Project registration & API keys** (teams register project → get API key; SDK sends key + project id as OTLP headers) | **Implemented** | `plans/backend.md` §4 → `backend/src/aiobs_backend/api/routes/projects.py` |
| **Backend: trace processing** (validate, normalize, enrich with business context, build workflow-level info) | **Implemented** | `plans/backend.md` §6 → `backend/src/aiobs_backend/ingest/pipeline.py` |
| **Backend: failure classification** (consume `sdk.error.*` + exception events + span status → failure tree) | **Implemented** | `plans/backend.md` §7 → `backend/src/aiobs_backend/classify.py` |
| **Backend: cost engine** (Phoenix pricing + attribution by client/project/workflow/agent/team) | **Implemented** | `plans/backend.md` §8 → `backend/src/aiobs_backend/cost.py` |
| **Backend: analytics & alerts** (consumption, error rate, budgets; cost thresholds) | **Implemented** (budget rules) | `plans/backend.md` §9–10 → `backend/src/aiobs_backend/analytics.py`, `alerts.py` |
| **Phoenix deployment** (self-hosted, containerized) | `sdk/dev/docker-compose.yml` | backend plan |
| **Dashboard** (engineering / manager / executive views) | **Implemented** | `plans/frontend.md` → `frontend/` |

## 6. Phased roadmap

| Phase | Scope | Status |
|---|---|---|
| **1 — SDK** | Everything in `plans/sdk.md`; mock-workflow harness passes in CI | **Implemented** (`sdk/`, CI in `.github/workflows/sdk.yml`) |
| **2 — Backend** | Trace processing, failure classification, cost engine, API keys/registration, Phoenix deployment | **Implemented** (`backend/`, plan in `plans/backend.md`, CI in `.github/workflows/backend.yml`) |
| **3 — Dashboard** | Engineering view first, then manager, then executive | **Implemented** (`frontend/`, plan in `plans/frontend.md`, CI in `.github/workflows/frontend.yml`) |
| **4 — Alerts & budgets** | Consumption/cost/latency/error-rate thresholds | Budget-based alerts implemented (backend); rule catalog extensible |

## 7. Cross-cutting decisions

- **SDK captures raw failure material; backend classifies.** The failure taxonomy lives in exactly one place (backend).
- **SDK records usage; backend computes cost** (Phoenix pricing server-side).
- **SDK manual workflow wrapper** provides business context (`client_id`, `project_id`, `workflow_id`, free-form context) — the foundation for cost attribution per client/workflow.
- **Mock workflows as the acceptance path**: deterministic scenarios with fixed tokens/inputs/outputs validate SDK capture now, and backend classification + cost computation when they exist (KPIs in `docs/05`).
- **No sampling in v1** — mock workflows require complete traces.

## 8. Deferred items

- Plain OpenAI/Anthropic client auto-instrumentation; LangChain memory/reranker tracing; CrewAI and other frameworks.
- Automated evaluation beyond mock workflows (LLM-as-judge style).
- Rate sampling; SDK packaging/naming decisions (PyPI, import name).
- Exact per-attempt retry counts (httpx event-hook client).

## 9. Out of scope

- Building the business agents being monitored.
- Replacing Phoenix (it remains the underlying trace infrastructure).
- Model training/fine-tuning; general-purpose IT monitoring.

## 10. References

- `docs/01` problem definition · `docs/02` process analysis · `docs/03` to-be solution · `docs/04` high-level architecture · `docs/05` KPIs
- `plans/sdk.md` — detailed SDK plan
- `.scratch/sdk/` — wayfinder map and decision tickets