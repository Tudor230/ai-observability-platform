# 01 — Backend read-surface enumeration

Type: research
Status: resolved

## Question

Enumerate the backend read surface so membership-based scoping and old-role
removal can be threaded through later tickets (06, 07). Produce a
per-endpoint inventory: for each router under `backend/src/aiobs_backend/api/routes/`,
list the endpoints, their `require_role(...)` gate, their `x-project-name`
scope handling, and any query-level scope filtering. Also list every
occurrence of `users.role`, `sdm`, `finance`, `require_role`,
`get_project_scope`, `x-api-key`, `AIOBS_READ_API_KEY` and the admin key
(`x-admin-key`) across `backend/src/`, with `file:line` references. Note the
role strings accepted by each `require_role` call so the new role→endpoint map
can be drawn.

## Answer

Full inventory captured in [research/01-backend-read-surface.md](../research/01-backend-read-surface.md). Highlights: role gates today are `("engineer","sdm")` → agents/executions, `("sdm","finance")` → clients/costs/workflows/budgets-status, any-user → alerts/metrics/overview, admin-key → the rest; `project_id` param and `x-project-name` are interchangeable on every scoped read (param unchecked); unscoped reads are `GET /alerts`, `GET /budgets/status`, and overview's `open_alerts`; `require_read_access` is dead code; `users.role` surfaces are enumerated; ingest auth is orthogonal and must not break.