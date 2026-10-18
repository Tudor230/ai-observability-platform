# 05 — Backend: execution API surface

Type: task
Status: resolved
Blocked by: 03
Area: loop detection, API
Estimate: S

## Comments

- 2026-10-17: `execution_dict` carries `loop_detected`/`loop_info`;
  `GET /executions` gains `loop=true|false` (omitted = both) wired through
  `exec_rows`. Covered by the API test in `backend/tests/test_loops.py`.

## Goal

Expose the flag for the dashboard: fields on list/detail plus a filter.

## Changes

1. `api/serialize.py` — execution payload gains `loop_detected` + `loop_info`.
2. `api/routes/executions.py` — `loop` query filter (`true`/`false`, omitted =
   both) on `GET /executions`, documented in the same style as the existing
   filters.
3. Tests: filter returns only looped / only clean; detail carries `loop_info`;
   existing filters unaffected.
