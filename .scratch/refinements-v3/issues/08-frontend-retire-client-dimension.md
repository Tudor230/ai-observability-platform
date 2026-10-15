# 08 — Frontend: retire the client dimension

Type: task
Status: open
Blocked by: 03, 04
Area: refinements v3, client dimension (ADR-0011)
Estimate: M

## Goal

Every dashboard surface that broke down or filtered by client breaks down or
filters by project instead.

## Changes

1. **Filters** — `FilterDimension` loses `client`
   (`components/FiltersControl.tsx`); `FiltersContext` stops parsing/writing
   `client_id`; `api/client.ts` `filterQuery` drops `client_id`; `types.ts`
   `Filters` and `AggregateRow.client_id` go away.
2. **Manager** (`pages/Manager.tsx`) — `useCosts("client")` → project; the
   "Cost by client" card and the "Clients" table are replaced by the merged
   two-view cards of ticket 09; drill-down links (`?client_id=`) become project
   links; the page subtitle drops "and client".
3. **Executive** (`pages/Executive.tsx`) — "Cost per client (service)" becomes a
   project card (ticket 09 shape); remove the Client column and any client
   drill-down.
4. **Engineering** (`pages/Engineering.tsx`) — remove the Client column; the
   project column renders `project_name`.
5. **Execution detail** (`pages/ExecutionDetail.tsx`, `lib/traceSpans.ts`) —
   drop the `client …` line/description fragment.
6. **Hooks** — delete `useClients` and `api.clients`; drop the `/clients` smoke
   expectation in any FE test fixture.
7. **Tests** — update `pages.test.tsx` fixtures/mocks (no client rows), keep
   the client *role* tests (`AuthContext.test.tsx` "hides cost data for the
   client role") untouched and passing.

## Acceptance

- No FE code path reads or renders client attribution; the RBAC client-role
  behaviour (nav, cost hiding, blocked Requests) is unchanged and still covered
  by tests.
- Cost and usage views answer "which project?" consistently.

## Tests

- `npm run test`, `npm run lint`, `npm run build`.
