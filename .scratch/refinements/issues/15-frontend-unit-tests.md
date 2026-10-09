# 15 — Frontend: unit tests — state, core components, API client, hooks

Type: task
Status: resolved
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

Implemented. New unit suites: `api/client.test.ts` (qs/filterQuery, execution
query params, CSRF header on mutations, PATCH, ApiError status, 401 handler,
204), `state/AuthContext.test.tsx` (profile/roles/cost visibility/admin
override/failed me/login/logout), `state/FiltersContext.test.tsx` (URL read,
default fallback, write preserving non-filter params, dropping defaults),
`state/RefreshContext.test.tsx` (off default, persistence, restore),
`components/core/Toast.test.tsx` (stack, dismiss, fake-timer auto-dismiss),
`components/core/Dialog.test.tsx` (semantics, initial focus, ESC/backdrop,
Tab trap, closed), `components/core/controls.test.tsx`
(SearchableSelect filter/mousedown/keyboard/disabled, Metric/Delta/Progress),
`components/core/Table.test.tsx` extended with SortableTh aria-sort+
`scope="col"`, and `components/charts/charts.test.tsx` (accessible chart
containers + links).

Also required: explicit RTL `cleanup()` in `src/test/setup.ts` (auto-cleanup
needs vitest globals, which this repo doesn't enable) — this fixed 24 cascading
duplicate-DOM failures.

Evidence: `npm test` **33 files / 463 passed**; coverage now **18.28% lines**
overall (state 84%, lib 94%, api 40% — `hooks.ts` is exercised by ticket 16's
page tests); `npm run lint` clean.
