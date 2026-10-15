# 11 — Frontend: searchable entity pickers

Type: task
Status: open
Blocked by: 07
Area: refinements v3, dropdowns
Estimate: M

## Goal

Every entity picker becomes a searchable, height-capped, scrolling combobox;
small fixed enums stay native selects.

## Changes

1. **Convert to `SearchableSelect`** (all currently native `<select>`):
   - `FiltersControl.tsx` / `TableFilters.tsx` — project picker (from
     `useDirectoryProjects`), value stays `project_id`, label is the name.
   - `Alerts.tsx` — rule scope pickers (department/team/project).
   - `Requests.tsx` — department/team pickers (role stays a native select).
   - `Pricing.tsx` — provider/model pickers where the list is data-driven.
   - `BudgetDialog.tsx` / `Accounts.tsx` — confirm all entity pickers already
     use `SearchableSelect` and carry a label.
2. **Keep native** — status, severity, time range, rows-per-page, role and
   other small enums (`components/core/Inputs.tsx` `Select`).
3. **Combobox polish** — confirm `.combobox__list` keeps `overflow-y: auto`
   with the measured `maxHeight`, and that flipping/portal behaviour applies to
   the newly converted pickers (including inside modals).
4. **Tests** — extend `components/core/controls.test.tsx`: filtering narrows
   options, keyboard navigation selects, list is capped and scrollable, and a
   converted picker inside `Dialog` is not clipped.

## Acceptance

- Long project/team/department lists are searchable by typing, never extend past
  their cap, and scroll with the keyboard or wheel.
- No entity picker regresses to a native OS dropdown.

## Tests

- `npm run test` (+ coverage gate), `npm run lint`, `npm run build`.
