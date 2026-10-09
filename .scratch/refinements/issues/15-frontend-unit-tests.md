# 15 — Frontend: unit tests — state, core components, API client, hooks

Type: task
Status: open
Blocked by: 14
Area: audit item 12 (coverage)
Estimate: L

## Goal

Cover the shared building blocks of the app with fast unit tests so page tests
(ticket 16) can focus on integration flows: state contexts, `components/core`,
the fetch wrapper, hooks, and chart components.

## Changes (tests to add)

1. **`src/state`**
   - `AuthContext`: profile loading → roles/hasRole/canApprove/costVisible
     derivation; 401 handler clears state; logout.
   - `FiltersContext`: URL-backed defaults, updates via `setFilters` write the
     URL with `replace`, invalid `days` falls back to 30 (after ticket 02).
   - `ThemeContext`: toggle persists and applies `data-theme`.
2. **`src/api/client.ts`**
   - `qs` encoding (skips undefined/empty); `filterQuery`; POST sends
     `content-type` + CSRF header; 401 triggers the unauthorized handler;
     non-OK throws `ApiError` with status/text; 204 handling.
   - Use `vi.stubGlobal("fetch", …)`; no network.
3. **`src/api/hooks.ts`**
   - Query-key shape for filters (including ticket 02 `q/sort/order`);
     `usePendingApprovals(enabled)` respects `enabled`.
4. **`src/components/core`**
   - `Table`/`SortableTh`: aria-sort cycling + click callback (ticket 02).
   - `Dialog`: opens/closes, ESC, focus lands inside, aria attributes.
   - `Feedback`/`Alert` variants; `EmptyState`; `Metric`/`Delta` tones
     (`up-is-bad` vs `down-is-bad`); `Progress` clamping only the bar.
   - `SearchableSelect`: filter, keyboard select, mouse-down selection.
   - `Toast` (ticket 12): stacking, auto-dismiss with fake timers, aria-live.
5. **`src/components/charts`**
   - `TrendChart` renders with data and shows an empty state with none;
     `BreakdownBars` renders labels/values (Recharts in jsdom with the
     ResizeObserver polyfill; assert on accessible text, not SVG internals).
6. **`src/lib`** — already covered; top up to 100% where cheap
   (`chartTheme`, `format` edge cases).

## Acceptance

- New tests are colocated (`*.test.tsx`/`*.test.ts`) and follow the ticket 14
  harness; no snapshots for behavior.
- Coverage on `src/state`, `src/api`, `src/components/core`,
  `src/components/charts`, `src/lib` ≥ 80% lines/statements/functions
  (measured locally with `npm run test:coverage`).
- All tests deterministic (fake timers where needed; no real fetch/Date
  dependence without mocking).

## Tests

- This ticket **is** the tests. Run `npm run test:coverage` and record the
  per-directory numbers in the comments; report any uncovered branch that
  needs a follow-up.

## Comments
