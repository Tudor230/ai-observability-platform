# 10 — Client role view

Type: prototype
Status: resolved
Blocked by: 06, 08

## Question

What does the client persona see?

Settled constraints (from charting): a distinct `client` role string with a
custom minimal read-only view, scoped to their project(s). Endpoint set settled
by 06: shared (overview, metrics, alerts) + traces (executions, workflows),
scoped; no costs. Route settled by 08: a dedicated `/client` page plus the
shared Overview; no engineering/manager/exec routes.

Prototype the page: which KPIs/data are surfaced, what is hidden, and the
navigation shape. Link the prototype as an asset on resolution.

## Answer

Prototype: [prototypes/10-client-view.html](../prototypes/10-client-view.html)
(rough dark-theme stub for discussion).

- **Route/sections**: dedicated `/client` page carrying KPI tiles,
  executions/errors trend, a workflow list with a **workflow drill-down
  (failure-kind breakdown)**, recent executions, and scoped alerts.
- **Trace depth**: execution summary + the **failure tree** (error
  classification); no raw spans/prompts, no cost.
- **Costs**: the client keeps the shared Overview, but the **backend strips
  cost fields for the client role** (data minimization) — not merely hidden in
  the UI.
- **Key minting**: clients cannot mint/rotate project keys; "any member" in 05
  means engineer/manager members.
- **Hidden**: costs/budgets, other projects, engineering/manager/exec views,
  org admin, key minting.