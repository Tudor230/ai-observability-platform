# 10 — Frontend: latency / error-rate / tool-call trend graphs

Type: task
Status: resolved
Blocked by: —
Area: audit item 10 (more graphs)
Estimate: S

## Goal

Add the missing reliability trends on top of data the API already returns
(`/metrics`), reusing `TrendChart`. No backend changes.

## Changes

1. **Overview — latency trend** (`pages/Overview.tsx`)
   - New `CardPanel` "Latency over time": two lines, `p50_duration_ms` and
     `p95_duration_ms` from `useMetrics("total", filters)`, `formatMs`
     formatter, legend, empty state ("No latency data in range").
2. **Overview — error-rate trend**
   - Add `error_rate` as a percentage-formatted line to a chart (either the
     existing "Executions over time" panel as a second series or a dedicated
     "Error rate" panel; prefer a second series so the correlation is visible).
   - Percentage values come as fractions (0..1) — multiply by 100 in the series
     mapping or format via `formatPct`.
3. **Manager — tool-call trend** (`pages/Manager.tsx`)
   - New panel "Tool calls per day": bar/line of `tool_calls` from the existing
     `trends` query already fetched on the page; `formatTokens`-style compact
     number or plain counts.
4. **Client page** (optional, small)
   - The executions/failed chart stays; add `p95_duration_ms` as a second line
     on a new small latency panel if it fits the client narrative (no cost).
5. All panels: loading skeleton, `QueryError` on error, `EmptyState` when the
   series is empty, consistent card spacing.

## Acceptance

- Overview shows cost, executions, tokens, latency (p50/p95) and error-rate
  trends; all respond to the global filters (days/project/client/workflow).
- Manager shows the tool-call trend; values match `/metrics` for the same
  filters.
- Charts render in both themes and at 900px width without overflow.
- Empty/error states are visible, never a blank card.

## Tests

- Covered by ticket 16 (Overview/Manager render assertions: chart titles and
  series presence with mocked metrics data); manual check against live data.

## Comments

Implemented with existing API data. Overview now shows a "Latency over time"
panel (p50/p95 lines, `formatMs`) beside Tokens and an "Error rate over time"
panel (`formatPct`) beside Open alerts; the series mapping gained
`p50_duration_ms/p95_duration_ms/error_rate`. Manager gained a "Tool calls per
day" panel beside the cost trend from the already-fetched metrics query.

Client-page latency panel (marked optional) was skipped — the client view is
already dense and the cost/error narrative there is covered.

Evidence: `npm run lint` + `npm run build` clean; `npm test` unaffected.
Render assertions for the new panels land in ticket 16.
