# 11 — Frontend: cost-by-model, team dimension, project page graphs

Type: task
Status: open
Blocked by: —
Area: audit item 10 (more graphs)
Estimate: M

## Goal

Expose the cost dimensions the API already supports (`/costs?dimension=model|team`)
as charts, and give the Project page its missing trends.

## Changes

1. **Executive — Cost by model chart** (`pages/Executive.tsx`)
   - Add a `BreakdownBars`/trend panel above or beside the existing "Cost by
     model" table, from `useCosts("model", filters)`; label `provider · model`;
     value label `formatMoney`; keep the table as the detailed view.
2. **Manager — Cost by team chart** (`pages/Manager.tsx`)
   - New panel from `useCosts("team", filters)`, rendered only when the caller
     is exec/admin (managers can call it too — the endpoint is manager/exec and
     scoped — confirm: scoped managers pass `require_access("manager","exec")`
     and costs do not reject team for scoped callers, unlike `/metrics`; so the
     panel can render for both. If a scoped caller receives aggregated rows,
     label them "unassigned" per the API fallback).
   - Show token/execution sublabels like the workflow/client panels.
3. **Project page charts** (`pages/Project.tsx`)
   - Add "Executions over time" and "Cost over time" panels using
     `useMetrics("project", {days, project_id}, projectId)` — the API already
     authorizes `dimension_key` against the caller's scope (404 outside).
   - Respect cost stripping: hide the cost panel when `costVisible` is false
     (client accounts never reach this page, but keep the guard consistent).
   - Loading/error/empty states like the other pages.
4. **Optional (same ticket): Projects list mini-sparkline**
   - Skip unless trivial; the per-row overview calls already exist.

## Acceptance

- Executive shows a cost-by-model visual that matches the table values for the
  same filters.
- Manager shows a cost-by-team panel whose rows match
  `/costs?dimension=team` for the caller's scope.
- Project page shows executions and cost trends scoped to that project only;
  changing the global days filter updates them.
- Charts have loading/error/empty states and work in both themes.

## Tests

- Covered by ticket 16 (Executive/Manager/Project render assertions with mocked
  API data, including the empty state); manual check of `/costs` vs chart
  values on the live stack.

## Comments
