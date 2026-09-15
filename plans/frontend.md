# Frontend / Dashboard Plan (v1)

Web dashboard for the **Agentic Observability and FinOps Platform** (phase 3 of
[`plans/implementation-plan.md`](./implementation-plan.md)). It is the presentation layer
that consumes the [backend Platform API](./backend.md) and nothing else — no direct
Postgres/Phoenix access (`docs/04 §4.4.9`). It implements the three user views defined in
`docs/03 §3.13` and validates the dashboard success criteria in `docs/05 §5.4`.

## 1. Purpose

Give engineers, service-delivery managers, and finance/executives a clear answer to the
four platform questions (`docs/03 §3.15`):

> **What did the agent do? How did it execute? How much did it consume? How much did it cost?**

One app, three role-scoped views, driven by the backend API.

## 2. Scope (v1)

- **Engineering view** — trace explorer, execution detail with span/failure tree, LLM/tool/
  retrieval breakdown, error + latency + token panels.
- **Manager (SDM) view** — cost per workflow/client, consumption trends, budget utilization,
  agent efficiency, alerts.
- **Executive view** — total AI cost, cost per client/service, cost per execution, cost
  trends, forecasts, unit economics.
- Shared shell: navigation, role switch, global filters (date range, client/project/workflow).

Out of scope for v1: real-time streaming push (polling is fine), auth/user management beyond
role switching, PDF/report export, custom-dashboard builder.

## 3. Tech stack

Matches `docs/04 §4.8`:

- **React** (Vite + TypeScript) — SPA.
- **Routing** — React Router (role-scoped routes).
- **State/data** — TanStack Query for server state + caching; lightweight local state for UI;
  no heavy global store needed in v1.
- **Charts** — Recharts (line/bar/area for time series, cost, trends).
- **Styling** — a component library + CSS (e.g. Mantine or MUI) with a dashboard layout;
  consistent design tokens (spacing, color for ok/error/severity).
- **API client** — typed client generated from the FastAPI OpenAPI schema (openapi-typescript).
- **Testing** — Vitest + React Testing Library (unit/component), Playwright (e2e) per repo
  e2e pattern.
- **Build/CI** — Vite build + a new `frontend.yml` workflow (mirroring `sdk.yml`).

## 4. App structure

```
frontend/
  src/
    api/            # typed client, hooks per resource (executions, costs, metrics, ...)
    components/     # shared UI (KPI card, table, filter bar, chart wrappers, alert badges)
    features/
      engineering/  # TraceExplorer, ExecutionDetail, SpanTree, FailureTree, LatencyPanel
      manager/      # CostByWorkflow, CostByClient, Trends, Budgets, Alerts
      executive/    # TotalCost, CostByService, UnitEconomics, Forecast
    layouts/        # AppShell (nav, role switch, global filters)
    routes/         # route definitions per role
    theme/          # design tokens, ok/error/severity colors
    App.tsx, main.tsx
  tests/            # unit + component (Vitest) and e2e (Playwright)
```

## 5. Shared shell & global filters

- **AppShell**: top nav (Overview, Engineering, Manager, Executive), role switcher
  (Engineer / SDM / Finance), and a global filter bar (date range, `client_id`,
  `project_id`, `workflow_id`).
- Filters are lifted into a shared query context and threaded into every API call; changing
  them re-fetches all visible panels (TanStack Query keys include the filters).
- Currency + unpriced-model display handled centrally (cost shown as USD; "unpriced" badge).

## 6. Engineering view

Consumes: `overview`, `executions`, `executions/{id}`, `executions/{id}/spans`.

- **TraceExplorer**: paginated execution table (name, workflow, client, status, duration,
  tokens, cost, started_at) with filters + a status filter (ok/error).
- **ExecutionDetail**: header (trace/execution identity, status, workflow version, business
  `metadata`), KPI strip (duration, tokens, cost, LLM/tool/retrieval calls, error count,
  retries), and:
  - **SpanTree**: hierarchical render of the normalized `spans` (kind icons for
    LLM/CHAIN/AGENT/TOOL/RETRIEVER; colored by status).
  - **FailureTree**: the backend's classified failure nodes with kind + message; drill to
    the failing span.
  - **LLM/Tool/Retrieval panels**: model, provider, tokens, latency, error.
- Engineering answer: *what happened + how it happened + what it consumed*.

## 7. Manager (SDM) view

Consumes: `workflows`, `clients`, `costs`, `metrics`, `alerts`, `budgets`.

- **CostByWorkflow / CostByClient**: bar lists with cost + tokens + success rate; click →
  drill into executions.
- **Trends**: time-series of cost, tokens, executions, latency (from `metrics`).
- **Budgets**: budget vs actual, utilization %, alert badges when over.
- **Alerts**: open/acknowledged/closed list with severity; filter by dimension.
- **AgentEfficiency**: per-agent cost + latency + error rate comparison.
- Manager answer: *cost per workflow/client, trends, budget utilization, agent efficiency*.

## 8. Executive view

Consumes: `overview`, `costs`, `metrics`.

- **TotalCost / TotalTokens** headline KPIs with period-over-period delta.
- **CostByService** (cost per client/project) and **CostByExecution** (avg cost/execution).
- **UnitEconomics**: cost per execution, per token, per successful execution.
- **Forecast**: simple trend projection from historical `metrics` (moving-average/linear
  fit; labeled as estimate).
- Executive answer: *total AI cost, cost per client/service/execution, trends, forecast,
  unit economics*.

## 9. API consumption contract

- Generated typed client from the backend OpenAPI (`/openapi.json`).
- TanStack Query hooks: `useExecutions(filters)`, `useExecution(id)`, `useCosts(...)`,
  `useMetrics(...)`, `useAlerts(...)`, `useOverview(...)`.
- Consistent loading/error/empty states; retry + staleTime tuned per view.
- The frontend never calls `/api/v1/pricing` or `/api/v1/projects` (admin) in v1 unless an
  admin UI is added.

## 10. KPIs / success criteria (`docs/05 §5.4`)

- **Dashboard validation**: for the mock-workflow executions, the information required by
  each view is available through the frontend — assert that:
  - engineering view renders the expected trace/span/failure data for a known mock scenario,
  - manager view shows the expected cost/workflow + budget values,
  - executive view shows total cost + per-client cost matching the backend.
- e2e (Playwright) against the running backend + docker stack: happy-path flows for the
  three views. Mirrors the `sdk.yml` e2e pattern (docker compose up, run, teardown).

## 11. Deferred / out of scope (v1)

- Real-time streaming / websockets (polling suffices).
- Auth provider / multi-tenant RBAC beyond a role switcher (backend scoping comes later).
- Admin UI for pricing/budgets/projects (API exists; UI deferred).
- Advanced analytics (custom dashboards, LLM-as-judge, forecasting models).

## 12. Decision index

Resolved during implementation on the wayfinder map `.scratch/frontend/` (per
`docs/agents/issue-tracker.md`):

| Ticket | Decision |
|---|---|
| [01 — Stack & scaffold](../.scratch/frontend/issues/01-stack-scaffold.md) | React 18 + Vite + TypeScript, TanStack Query, React Router, Recharts, dark tokens |
| [02 — Routing & shell](../.scratch/frontend/issues/02-routing-shell.md) | AppShell + role switcher (Engineer/SDM/Finance) + global filters context |
| [03 — API client](../.scratch/frontend/issues/03-api-client.md) | Typed fetch client + query hooks; dev + nginx `/api` proxies |
| [04 — Views](../.scratch/frontend/issues/04-views.md) | Overview / Engineering (span+failure tree) / Manager (cost, budget, alerts) / Executive (unit economics + forecast) |
| [05 — Code-splitting](../.scratch/frontend/issues/05-code-splitting.md) | Lazy pages + vendor/charts chunks |
| [06 — Phoenix design system](../.scratch/frontend/issues/06-phoenix-design-system.md) | Arize Phoenix design system: tokens, side-nav shell, core components, themed charts; Geist fonts; dark default + light toggle |

---

## Redesign (2026-09-15): Phoenix design system

The dashboard was re-skinned to faithfully match the **Arize Phoenix** UI
(Apache-2.0) shipped at `:6006`, so the platform and Phoenix read as one
product:

- **Tokens** (`src/theme/tokens.css`): Phoenix's dimension scale, color ramps
  (`-rgb` companions), semantic aliases, text opacities, rounding, borders,
  table/badge/card/field/button/chart tokens and z-index bands. Dark is the
  default; `.theme--light` provides the light palette and the sidebar toggle
  persists the choice.
- **Shell**: collapsible side nav (52/260px) with brand, separators and theme
  toggle; top nav with breadcrumbs, open-alert counter and persona select;
  every page is `page` → `PageHeader` → `FilterToolbar` → content.
- **Primitives** (`src/components/core/`): Card, Badge (LCH variants), Table,
  Tabs, Button, Alert, Field/Select, Progress, Metric, Skeleton, EmptyState,
  inline icon set — BEM classes, no CSS-in-JS dependency.
- **Charts**: Recharts bound to Phoenix chart tokens via `useChartTheme`
  (themed gridlines, axes, tooltip panel); horizontal breakdown bars for
  per-dimension cost.
- **Type**: Geist Sans/Mono self-hosted via `@fontsource` (offline-safe).


---

## Implementation status (2026-09-15)

Shipped as planned, with these deltas (see `docs/06-project-audit.md` �7):

- **Role switcher**: presentation-level role gating (nav + routes, persisted);
  server-side RBAC is opt-in via user keys (roles engineer/sdm/finance/admin).
- **Filters**: days/project/client/workflow thread into overview, executions,
  metrics/trends/forecast; alerts and budget status are intentionally global.
- **Agent efficiency**: panel backed by `/agents` (per-execution aggregation).
- **Failure tree**: rendered hierarchically; execution detail distinguishes
  404 from backend failures; all views show explicit error banners.
- **Forecast**: linear projection anchored to today, labeled as an estimate,
  with an "insufficient data" state.
- **Deferred**: pagination/status-filter UI in the Engineering table,
  chart-to-execution drill-downs, Playwright page tests (CI covers tsc, ESLint,
  Vitest and the production build).
