# 03 — Backend: `GET /margin`

Type: task
Status: resolved
Blocked by: 02
Area: margin, read API
Estimate: M

## Goal

One endpoint that answers "what do we earn, what does it cost, where is the
margin going, and at what volume does it break even?".

## Changes

1. **`api/routes/margin.py`** — per-day version resolution over the window,
   proration (`month ≡ 365/12`, `year ≡ 365`), per-project rows with `rate`,
   `covered_days`, `revenue`, `manual_cost`, `ai_cost`, `margin`, `margin_pct`,
   `executions`, `cost_per_execution`, `break_even_scale`,
   `break_even_executions`; `totals` with coverage (projects rated, share of AI
   cost on covered days); a daily `series` for the margin-over-time chart.
2. **Access** — `require_access("exec")` (admin bypass); `days`/`start`/`end`
   window like the other read routes.
3. **Tests** — a mid-window rate change prorates as a step; uncovered days
   contribute no revenue but their cost stays in the totals; an unrated project
   has `rate`/`margin` null while its cost counts; break-even is null when AI
   cost is 0; empty window; manager/client 403.

## Acceptance

- Totals are conservative and coverage is reported, so a partial rate book is
  obvious.
- Worst margin sorts first, then unrated projects by AI cost.

## Tests

- `uv run pytest`, `uv run ruff check .`, `uv run mypy src`.

## Result

- `GET /margin` resolves the active version per day, prorates revenue and
  manual cost (`month ≡ 365/12`, `year ≡ 365`), and returns per-project rows
  (rate, covered/window days, revenue, manual cost, AI cost, margin, margin %,
  executions, cost/execution, break-even scale and executions), conservative
  totals with coverage, a daily series and the window.
- Internal projects are excluded from the margin totals and coverage and
  reported as `internal_cost` instead; the flag overrides their rate versions.
- Evidence: `tests/test_margin.py` — 6 tests: mid-window version proration with
  a real step, uncovered cost in the conservative total, manual cost reducing
  the contribution, internal projects never scored as a loss, the no-rate case
  (revenue 0, coverage 0, cost still visible) and the empty window.
