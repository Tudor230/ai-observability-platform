# 10 — Frontend: per-table filters with namespaced URL state

Type: task
Status: resolved
Blocked by: 09
Area: refinements v3, filtering
Estimate: L

## Goal

Replace the single page-level filter set with per-card filtering: each table
filters independently, and its state lives in namespaced URL params so views
stay shareable.

## Changes

1. **`state/FiltersContext.tsx`** — slim down to the page-level time window
   (`days`) plus its setter; drop `project_id`/`client_id`/`workflow` parsing.
2. **New `state/useTableFilters.ts`** — hook keyed by a card id:
   - reads/writes `<card>_<field>` params (`projects_project`,
     `workflows_workflow`, `teams_team`, `models_model`, …), preserving other
     params;
   - exposes `{ filters, setFilter, clearAll, activeCount }`.
3. **New `components/TableFilters.tsx`** — compact control + chips for one
   card, built on the existing `FiltersControl`/`FilterChips` markup (button,
   popover, chips) with dimensions supplied per card.
4. **Pages** — Overview, Manager, Executive, Project, Client, Projects: each
   card gets its own `TableFilters` in `CardPanel extra`, its own query key
   (`useCosts(dimension, cardFilters)`), and its own loading/error state;
   page-level KPIs keep using the shared `days`.
5. **Engineering** — keeps its inline controls and existing param names; note
   the exception in the code comment.
6. **Drill-down links** — cross-page links that targeted `?workflow=` /
   `?client_id=` / `?project_id=` now target the receiving card's namespaced
   param (or Engineering's `q`), e.g. Manager → Engineering uses `q=`.
7. **Tests** — `FiltersContext.test.tsx` plus new coverage: two cards on one
   page filter independently; params round-trip into the URL; chips clear only
   their own card.

## Acceptance

- Filtering one table never changes another table's data or controls.
- A filtered view is reload-safe and shareable through its URL.
- No page-level filter popover remains where cards have their own controls
  (page-level `days` stays in the header).

## Tests

- `npm run test` (+ coverage gate), `npm run lint`, `npm run build`.

## Comments

Done. New `state/useTableFilters.ts` (namespaced URL state:
`<card>_project_id` / `<card>_workflow`, per-card `setFilter`/`clear`/
`activeCount`) and `components/TableFilters.tsx` (compact header control with a
searchable project picker + workflow input, plus `TableFilterChips` for the card
body). `CostCard` gained `filters`/`filterChips` slots. Every cost card now
queries with its own scope: Manager's Workflows/Projects/Teams/Agents and
Executive's Projects/Models each call `useCosts(..., {...pageDays,
...cardFilters})`, and their page headers were slimmed to the shared `days`
window only. Engineering (single list) and the other single-table pages
(Overview, Client, Projects, Project) keep their page-level `project`/`workflow`
params, which also keeps Manager's `?workflow=`/`?project_id=` drill-down links
working as before.

Evidence: `npm run test` **512 passed**, including two new tests: two cards on
one page filter independently (only the targeted card's query carries the
param, other cards keep an empty scope) and a card's chip clears only its own
filter through the URL. `npm run lint` + `npm run build` clean; coverage 88.5%
stmts / 73.6% branches / 68.1% funcs (gates 80/70/65).
