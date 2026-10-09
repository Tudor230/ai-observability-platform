# 02 — Frontend: Engineering search/sort + URL-persisted filters

Type: task
Status: open
Blocked by: 01
Area: audit item 4 (search / sort)
Estimate: M

## Goal

Make the execution list searchable and sortable, and make the global filter
state shareable/bookmarkable by moving it into the URL. Introduce a reusable
sortable table header primitive.

## Changes

1. **`src/components/core/Table.tsx`**
   - New `SortableTh` (or `Th` props): `sortKey`, `active`, `direction`,
     `onSort`, `aria-sort="ascending|descending|none"`, button inside the
     header cell, focus styles. Export from `components/core/index.ts`.
2. **`src/state/FiltersContext.tsx` — URL-backed filters**
   - Initialize state from `useSearchParams()` (`days|project_id|client_id|workflow`,
     `days` default 30) and write changes back with `replace` (no history
     spam). One source of truth; downgrade the in-memory state to a derived
     value from the URL.
   - Manager drill-down links (`/engineering?workflow=…`) now work through the
     generic mechanism; remove the one-shot `appliedDrilldown` effect in
     `pages/Engineering.tsx:37-45`.
   - Non-Engineering pages keep using `useFilters()` unchanged (API identical).
3. **`src/api/client.ts` + `src/api/hooks.ts`**
   - `api.executions(f, opts)` gains `q`, `sort`, `order`; `useExecutions`
     accepts them and includes them in the query key.
4. **`src/pages/Engineering.tsx`**
   - Debounced search input (300 ms) bound to URL `q`.
   - Sortable columns: Started, Duration, Tokens, Cost, Status; clicking toggles
     `order` and sets `sort` in the URL.
   - `status` filter also URL-backed (replaces local `useState`).
   - Detail: keep the current "Load more" behavior in this ticket (pagination is
     ticket 13) but make `limit` URL-aware so ticket 13 can build on it.
5. **`src/pages/Manager.tsx`** (optional, same ticket)
   - Client-side sorting for the small Workflows/Clients/Agents tables using
     `SortableTh` with local state (no API change).

## Acceptance

- Typing in the Engineering search filters results server-side after the
  debounce; clearing restores the full list.
- Clicking a column header sorts; the indicator and `aria-sort` reflect state;
  clicking toggles asc/desc.
- Copy-pasting the URL reproduces search + sort + status + global filters
  exactly (fresh tab).
- Manager cost-drill-down links still scope the Engineering list on arrival.
- No regressions on Overview/Manager/Executive/Client pages that use
  `useFilters`.

## Tests

- Manual: the flows above against the running stack (search/sort/URL
  round-trip).
- Covered automatically by ticket 16 (Engineering page RTL tests); add
  `SortableTh` interaction tests in ticket 15.

## Comments
