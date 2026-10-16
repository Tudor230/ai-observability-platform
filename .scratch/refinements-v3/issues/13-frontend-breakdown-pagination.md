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

Evidence: `npm run test` **514 passed** — the breakdown test asserts the bars
sit inside `.card-scroll`, the footer is its immediate next sibling, and the
"Showing …" text is excluded from the scroll area; `npm run lint` +
`npm run build` clean; coverage 88.5% stmts / 74.1% branches / 68.4% funcs
(gates 80/70/65).