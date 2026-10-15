# 10 — Frontend: per-table filters with namespaced URL state

Type: task
Status: open
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
