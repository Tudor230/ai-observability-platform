# 02 — Frontend: cost-card detail tables stop overflowing to the right

Type: task
Status: resolved
Blocked by: 09 (refinements v3, cost-card tables)
Area: phoenix insights, table UX
Estimate: S

## Goal

With `.table-wrap--capped { overflow: hidden }` (refinements v3) a long project
name widened the auto-layout table and **clipped the right column** — the Cost
value could disappear. The label column must be a fixed width, trim with an
ellipsis, and reveal the full text on hover.

## Changes

1. **`theme/components.css`** (scoped to `.table-wrap--capped`):
   - `table-layout: fixed` on `.table`;
   - the first column takes a fixed `40%` — the remaining columns then split the
     rest evenly under fixed layout (15% each on 5-column cards, 20% on the
     4-column Models card), so the table can never exceed the card;
   - `white-space: nowrap` on the non-primary cells so headers and numbers stay
     on one line.
2. **`components/CostCard.tsx`** — the primary cell keeps `table__cell--primary
   truncate` (now effective) and gains
   `title={row.bar?.label ?? row.key}` for the native hover reveal.
3. **Tests** — the detail table's primary cell exposes the full label via
   `title`; existing 6-row paging and sorting assertions stay green.

## Acceptance

- No horizontal overflow in any cost card; the Cost column is always visible.
- Hovering a trimmed label shows the full text (native tooltip).
- Engineering and every other table are untouched.

## Tests

- `npm run test`, `npm run lint`, `npm run build`.

## Result

- `.table-wrap--capped .table { table-layout: fixed }` plus a `34%` first
  column (the numeric columns split the remainder, so the table is always 100%
  of the card at every viewport width — the minimum card is 420px, collapsing
  to a single column on phones), keeping `.truncate` on the label, and the full
  label on the cell's `title`.
- Test asserts the primary cell keeps `truncate` and exposes `title="wf-0"`.
- Evidence: 516 frontend tests pass, lint + build clean.
