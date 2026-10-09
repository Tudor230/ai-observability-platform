# 13 — Frontend: executions pagination, empty-state CTAs, accessibility pass

Type: task
Status: open
Blocked by: 02 (aria-sort part)
Area: audit item 11 (UX)
Estimate: M

## Goal

Replace the unbounded "Load more" with real pagination, remove dead-end empty
states, and fix the small accessibility gaps across tables, charts and dialogs.

## Changes

1. **Engineering pagination** (`pages/Engineering.tsx`)
   - Replace "Load more" with prev/next + page-size selector (25/50/100) and a
     "showing X–Y of N" summary using `total` from the API.
   - Page state (`page`, `limit`) lives in the URL (ticket 02 already moved
     filters there); changing filters/search/sort resets to page 1.
   - Keep the fetching indicator; disable buttons at bounds; no data loss on
     page changes.
2. **Empty-state CTAs** — every empty state that references an action links to
   it:
   - Engineering: "Open Requests to register a project" link (already hints;
     make it a link) + "Configure pricing" link;
   - Manager budgets: button opening the create dialog (ticket 04);
   - Manager/Overview alerts: "Configure rules" link for managers →
     `/alerts?tab=rules` (ticket 09 deep-link support);
   - Projects: link to `/requests` (already exists — verify);
   - Pricing (new): CTA in its empty state (ticket 05).
3. **Accessibility pass**
   - Tables: visually-hidden `caption` per table, `scope="col"` on headers
     (extend `Th` default), `aria-sort` from ticket 02.
   - Charts: wrap each `TrendChart`/`BreakdownBars` in a figure with
     `role="img"` + `aria-label` describing the series (pass a prop), and a
     visually-hidden series summary or rely on the adjacent table.
   - Dialogs (`components/core/Dialog.tsx`): verify focus trap, initial focus,
     ESC close, `aria-modal`/`aria-labelledby`; fix if missing.
   - Buttons with icon-only content have `aria-label` (audit existing usages).
   - Focus-visible rings on interactive table rows and nav links.
4. **No visual redesign**: spacing/typography stay as-is.

## Acceptance

- Engineering navigates pages 1..N with correct ranges, disabled bounds, and
  shareable URLs; changing days/status/search resets to page 1.
- Every empty state with an actionable message links to the action; no
  "create X" dead ends remain.
- Axe-style manual check: tables have captions/scope, charts have accessible
  names, dialogs trap focus and close on ESC.
- Keyboard-only walkthrough of Engineering (sort, search, paginate) works.

## Tests

- Ticket 15: `Dialog` focus/ESC tests, `Table` caption/scope rendering tests.
- Ticket 16: Engineering pagination interaction test; checklist for the
  manual a11y pass recorded in the PR/comments.

## Comments
