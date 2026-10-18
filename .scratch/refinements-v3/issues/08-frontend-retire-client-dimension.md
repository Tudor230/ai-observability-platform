# 08 — Frontend: retire the client dimension

Type: task
Status: resolved
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

## Comments

Done. The FE no longer knows the client dimension: `FilterDimension`/`Filters`/
`AggregateRow`/`BudgetInput`/`BudgetStatus` lost their client fields,
`FiltersContext` stopped parsing/writing `client_id`, `filterQuery` dropped it,
`api.clients` + `useClients` are gone, and `BudgetDialog` lost its "Client
filter". Manager's "Cost by client" card is now "Cost by project" (drill-down
`/engineering?project_id=…`) and the "Clients" table became a "Projects" table
built from the rich `/costs?dimension=project` rows (executions, error rate,
tokens, cost) with names resolved through the new `useProjectNameMap()` hook;
Executive's "Cost per client (service)" became a "Projects" detail table (cost,
executions, error rate, last seen). Engineering's Client column shows the
project name; `ExecutionDetail` and `traceSpans` dropped client fragments. The
client *role* behaviour (cost hiding, nav, blocked Requests) is untouched.

Evidence: `npm run test` **509 passed** (fixtures/mocks/client-role test
updated); `npm run lint` + `npm run build` clean; coverage 88.5% stmts / 73.2%
branches / 68.4% funcs (gates 80/70/65); `npm run typecheck` clean.
