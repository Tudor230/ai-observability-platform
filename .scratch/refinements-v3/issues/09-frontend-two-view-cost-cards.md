# 09 — Frontend: two-view cost cards, capped tables, shared pagination

Type: task
Status: open
Blocked by: 04, 08
Area: refinements v3, table UX
Estimate: L

## Goal

Cost breakdown cards become two-view (breakdown ⇄ detail), and long breakdown
tables get a height cap with paging.

## Changes

1. **Shared pager** — extract Engineering's inline pagination controls into
   `components/core/Pagination.tsx` (props: `page`, `pageSize`, `total`,
   `onPage`, optional `pageSizeOptions`, labels via `aria-label`), and switch
   `Engineering.tsx` to it without behaviour change.
2. **Capped tables** — `TableWrap` gains a `capped` variant (max-height
   ~380px, `overflow-y: auto`, sticky header already supported by the scroll
   container) in `theme/components.css`.
3. **Two-view cards** — new `components/CostCard.tsx` (or equivalent) rendering
   `Tabs` with `breakdown` | `detail` views:
   - *breakdown*: the existing `BreakdownBars` with drill-down links.
   - *detail*: capped, paged table (10 rows/page via the shared `Pagination`)
     with columns keyed on the dimension — executions, error rate, tokens,
     cost, avg duration, last seen — fed by the rich `/costs` rows (ticket 04);
     cost cells respect `costVisible`.
4. **Manager** — replace the cost-by-workflow / cost-by-client / team cards with:
   `Projects` (two views) and `Workflows` (two views); keep the team card as a
   breakdown with cap + paging.
5. **Executive** — apply the same two-view shape to its cost cards
   (project/model, plus any other dimension card present).
6. **Tests** — `pages.test.tsx`: view switch renders both panels, pager moves
   between pages, cost remains hidden for client-only profiles.

## Acceptance

- Every cost/breakdown table is height-capped, scrolls with a sticky header,
  and pages at 10 rows.
- Switching views never refetches (both views read the same query result) and
  preserves the card's filters (ticket 10).
- Engineering pagination behaves exactly as before.

## Tests

- `npm run test` (+ coverage gate), `npm run lint`, `npm run build`.
