# 06 — Frontend: loop badge, filter and detail section

Type: task
Status: resolved
Blocked by: 05
Area: loop detection, dashboard
Estimate: M

## Comments

- 2026-10-17: `LoopInfo` type + `Execution.loop_*` fields + `loop` query
  option; loop badge with signal-summary tooltip on Engineering and Client
  tables; "Looped"/"Clean" filter in Engineering; loop panel on the execution
  detail; `loop_executions` label in the Alerts rule form. `lib/loops.ts`
  helper with its own tests; page tests for badge, filter param and detail
  panel. Frontend suite 538 passed, typecheck + lint clean.

## Goal

Make looped executions visible and investigable, and teach the Alerts page the
new metric.

## Changes

1. `api/types.ts` — `Execution.loop_detected` / `loop_info`; `AlertRuleMetric`
   gains `loop_executions`.
2. Executions table (Engineering page + wherever the list renders) — loop badge
   next to the status cell; tooltip with signals/counts.
3. Filters control — "Looped" entry (any/only/exclude) wired to the API filter.
4. `ExecutionDetail.tsx` — loop section: signals, max repeat counts, cycle step
   names when present.
5. `Alerts.tsx` — metric label for `loop_executions`.
6. Tests: badge renders, filter sets the query param, detail renders loop info,
   metric label covered by the existing alert-rules tests.
