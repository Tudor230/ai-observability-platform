# 07 — Docs + end-to-end proof

Type: task
Status: in progress
Blocked by: 02, 03, 04, 06
Area: loop detection, docs
Estimate: S

## Goal

Close the loop: documentation matches the implementation and one demo run
proves SDK → backend flag → alert → UI.

## Changes

1. `sdk/README.md` — loop detection section: signals, thresholds, signature
   privacy (salted, run-scoped), `loop_detection` off switch.
2. `backend/README.md` + `plans/backend.md` §10 — loop re-derivation, config
   knobs, `loop_executions` metric.
3. Demo: run the looping mock scenario against the local stack; verify
   `GET /executions?loop=true` shows the flag, `loop_info` is populated, and
   the seeded rule trips after the window threshold.
4. `docs/06-project-audit.md` — note the feature if that file tracks delivered
   capabilities.
