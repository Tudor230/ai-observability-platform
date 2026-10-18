# 01 — Contracts: loop attribute names + ADRs

Type: task
Status: resolved
Blocked by: —
Area: loop detection (ADR-0014)
Estimate: S

## Comments

- 2026-10-17: `SDK_CALL_SIG`/`SDK_LOOP_*`/`LOOP_SIGNAL_*`/`LOOP_DEFAULT_THRESHOLD`/
  `LOOP_CYCLE_MAX_STEPS` + `LoopStep`/`LoopScan`/`scan_loop_steps` landed in
  `shared/aiobs_contracts` (the scan is shared so SDK and backend cannot
  drift). ADR-0014 written; ADR-0003 amended with the salted-signature clause;
  `CONTEXT.md` gained **Loop flag** and **Call signature** glossary entries.

## Goal

Define the shared vocabulary once (both sides import `aiobs_contracts`) and
record the decisions.

## Changes

1. `shared/aiobs_contracts/src/aiobs_contracts/__init__.py`
   - `SDK_CALL_SIG = "sdk.call.sig"` (salted per-call signature, LLM/TOOL spans).
   - Loop evidence attributes: `SDK_LOOP_SIGNAL = "sdk.loop.signal"`,
     `SDK_LOOP_REPEAT_COUNT = "sdk.loop.repeat_count"`,
     `SDK_LOOP_TOOL_REPEATS = "sdk.loop.tool_repeats"`,
     `SDK_LOOP_LLM_REPEATS = "sdk.loop.llm_repeats"`,
     `SDK_LOOP_CYCLE_REPEATS = "sdk.loop.cycle_repeats"`.
   - Signal constants `LOOP_SIGNAL_TOOL = "tool_repeat"`,
     `LOOP_SIGNAL_LLM = "llm_repeat"`, `LOOP_SIGNAL_CYCLE = "cycle"` and
     `LOOP_SIGNALS` frozenset.
   - `LOOP_DEFAULT_THRESHOLD = 3`, `LOOP_CYCLE_MAX_STEPS = 4` (SDK live marks
     use these; backend owns the authoritative copies as config).
2. `docs/adr/0014-loop-detection-flag-and-signatures.md` — loop is a flag (not
   a failure kind), signature-based within-execution detection, salted
   run-scoped hashes, SDK measures / backend decides.
3. `docs/adr/0003-retention-and-payload-handling.md` — amendment note under
   Decision: salted signature hashes are derived, run-scoped, non-reversible
   evidence; they ride the span stream even when capture is off.
4. `CONTEXT.md` — glossary entries for **Loop flag** and **Call signature**.
