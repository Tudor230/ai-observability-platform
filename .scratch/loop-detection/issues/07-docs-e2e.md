# 07 — Docs + end-to-end proof

Type: task
Status: resolved
Blocked by: 02, 03, 04, 06
Area: loop detection, docs
Estimate: S

## Comments

- 2026-10-17: SDK README got the loop-detection section (signals, signature
  privacy, off switch, demo scenarios); backend README + `plans/backend.md` §10
  document re-derivation, env knobs, the `loop_executions` metric and the
  `loop=true|false` filter. `docs/06-project-audit.md` is a dated snapshot of
  an older commit, so it was left untouched.
- 2026-10-17: end-to-end demo captured against the live docker stack (fresh
  images with the new code + migration): `loop_clean_react` stays clean, five
  `loop_tool_repeat` runs flag `ok` executions with all three signals, and the
  seeded warning fires. Screenshots + API transcripts in
  `.scratch/loop-detection/demo/`.

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
