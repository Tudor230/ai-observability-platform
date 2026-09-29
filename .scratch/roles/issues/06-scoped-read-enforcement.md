# 06 — Scoped read enforcement

Type: grilling
Status: resolved
Blocked by: 01, 03, 04

## Question

How is team-scoped read access enforced?

Settled constraints (from charting): engineer/manager see their team's
projects; exec/admin see all; client sees own projects; ingest auth unchanged.

Decide:
- How the allowed-project scope is derived from approved memberships (see 01
  for the endpoint inventory, 03 for the derivation).
- How it threads through the read routers (executions, agents, clients, costs,
  workflows, budgets, overview, metrics, alerts).
- Interaction with the `x-project-name` header, the service read key
  (`AIOBS_READ_API_KEY`), the admin key, and demo open mode.
- The new role→endpoint mapping replacing `require_role("engineer", "sdm")`
  and `require_role("sdm", "finance")`.

## Answer

Decided:

- **Role → endpoint map**:
  - `engineer`: executions (list/detail/spans/failures), agents, workflows,
    + shared — scoped.
  - `manager`: engineer's set + business (costs, clients, budgets/status) —
    scoped.
  - `exec`: business (costs, clients, workflows, budgets/status) + shared,
    global — **no trace detail** (executions/agents); persona segregation
    preserved.
  - `client`: shared + traces (executions, workflows), scoped to their
    project(s) — **no costs**.
  - `admin`: everything (implicit bypass).
  - Shared = overview, metrics, alerts, for all authenticated roles.
- **Enforcement**: one shared `require_access(*roles)` dependency resolves the
  caller (session cookie or user API key) and derives the allowed-project set
  from approved memberships (union per 03); routers intersect it with the
  requested `project_id` / `x-project-name`; an out-of-scope requested project
  returns **404**; list results are filtered silently.
- **Alerts and budgets/status are scoped by the allowed set**: rows whose
  project resolves into it; client/workflow dimensions mapped via allowed
  projects; global/total rows visible only to exec/admin.
- **Read auth**: reads require a session or user API key, scoped identically;
  the admin key and the service read key (`AIOBS_READ_API_KEY`) bypass scoping;
  **implicit demo open-reads are removed** and the dead `require_read_access`
  is dropped.

Added by 08: expose a **non-admin, scoped `GET /projects`** (the caller's
allowed projects, id + name) so the frontend project filter has a scoped
source.

Added by 10: for the **client role the backend strips cost fields** from shared
payloads (data minimization, not UI-only hiding).