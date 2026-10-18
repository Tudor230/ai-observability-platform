# 13 — Frontend: limit + paginate the breakdown view too

Type: task
Status: resolved
Blocked by: 09
Area: refinements v3, table UX (amendment to 09)
Estimate: S

## Goal

The two-view cost cards paged only their *detail* table; the breakdown (bars)
rendered every row. Both views must show the same, bounded page of rows.

## Changes

1. **`components/CostCard.tsx`** — one page state shared by both views; the
   breakdown renderer now receives only the visible rows
   (`breakdown: (visible: CostDetailRow[]) => ReactNode`), and the shared
   `Pagination` control renders under the bars as well as under the table.
   `CostDetailRow` carries `href` + `bar` (label/value/valueLabel/sublabel), so
   the caller builds each row once and both views read from it; the new
   `CostCardBars` helper maps visible rows onto `BreakdownBars`.
2. **Manager / Executive** — every card (Workflows, Projects, Teams, Agents,
   Models) builds rows once with `href` + `bar` and passes
   `breakdown={(visible) => <CostCardBars rows={visible} />}`.
3. **Tests** — new "limits and pages the breakdown view too" (12 rows: 10 bars
   on page 1, `Showing 1–10 of 12 rows`, Next → 2 bars, `Showing 11–12 of 12
   rows`); the detail pager test scoped to its own card.

## Acceptance

- A 12-row dimension shows 10 breakdown bars plus a pager; paging moves both
  views (the page is shared, so switching tabs keeps the page).
- Bar widths stay relative to the visible page (they were already relative to
  the rendered set).

## Tests

- `npm run test` (+ coverage gate), `npm run lint`, `npm run build`.

## Comments

Done. `CostCard` owns a single page for both views and hands the breakdown
renderer only the visible rows; `CostCardBars` maps them onto `BreakdownBars`
(reusing `row.href` so bar links and detail links never diverge). All six cards
across Manager and Executive were rewired, and the four Manager cards plus the
two Executive cards each gained the pager in the breakdown view.

**Amendment (same commit):** both views now share the same visual contract as a
table — the breakdown renders inside a capped, scrollable `.card-scroll`
(380px, via the new `--card-scroll-max-height` token shared with
`.table-wrap--capped`), and the pager moved into a `.card__pager` footer with a
top border, a sibling *after* the scroll area in both views, so it stays put at
the bottom of the table while the content scrolls and never scrolls away.

**Amendment 2 (same commit):** the shared height became *fixed*, not a cap
(`--card-scroll-height: 380px`; both `.table-wrap--capped` and `.card-scroll`
use `height`, keeping `overflow` for the inner scroll), so switching Breakdown ⇄
Detail never resizes the card. Loading and empty states render the same content
in both tabs, so the card is size-stable there too, and the empty/loading paths
were already outside the scroll area.

**Amendment 3 (new commit):** no inner scrolling at all. The shared body is a
fixed 360px (`--card-scroll-height`) and a whole page fits inside it: pages are
6 rows, the breakdown rhythm is compacted (`.card-scroll .breakdown` padding/gap
8px, row gap 2px, sublabels truncate to one line) so six bars ≈ 338px, and the
detail rows are matched to the bars' height (`.table-wrap--capped .table tbody
tr { height: 50px }`) so six rows + header ≈ 337px. `CostCard`'s default
`pageSize` is now 6 and the primary detail cell truncates, keeping every row
single-line so the arithmetic always holds. Overflow is `hidden` on both
bodies — the remainder is paginated, never scrolled.

Evidence: `npm run test` **514 passed** — the paging tests assert 6 rows per
page in both views (12-row fixture: `Showing 1–6 of 12 rows` → Next →
`Showing 7–12 of 12 rows`), the bars sit inside `.card-scroll`, and the pager
footer is its immediate next sibling; `npm run lint` + `npm run build` clean;
coverage 88.5% stmts / 74.1% branches / 68.4% funcs (gates 80/70/65).

**Amendment 4 (new commit):** the detail table is sortable by every column,
exactly like the Engineering table — each header is a `SortableTh` (click to
sort descending, click again to flip, `aria-sort` + ↕/▲/▼ indicator). Sorting is
client-side over the card's full row set, driven by the new `CostDetailRow
.sortValues` (raw values parallel to `cells`): numbers compare numerically,
everything else as case-insensitive text, and the sort is stable so ties keep
the incoming cost ranking. It is a *detail-view* concern — the breakdown keeps
the incoming order — so the two views now page independently (the shared
`page` state became `breakdownPage` + `detailPage`, and the pager is rendered
per view). Every row map on Manager (4 cards) and Executive (2 cards) supplies
`sortValues`.

Evidence: `npm run test` **515 passed** (new test: 5 header sort controls, text
and numeric columns both flip desc ⇄ asc, `aria-sort` on the active header, a
new column restarts descending, and the breakdown order is unchanged after
sorting the detail); `npm run lint` + `npx tsc -b --noEmit` + `npm run build`
clean; coverage 88.6% stmts / 74.2% branches / 68.6% funcs (gates 80/70/65).