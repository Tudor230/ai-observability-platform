# 03 — Backend: loop classification on ingest

Type: task
Status: resolved
Blocked by: 01
Area: loop detection, backend ingest
Estimate: L

## Comments

- 2026-10-17: `spans.call_sig` (+ `(execution_id, call_sig)` index) and
  `executions.loop_detected`/`loop_info` added with migration
  `b7c1e5a9d3f2`; `_derive_loops` in the ingest pipeline re-derives the flag
  from stored signatures after every upsert batch with the shared scanner and
  the new `loop_*` settings. 8 integration tests in `backend/tests/test_loops.py`
  (repeats, cycles, below-threshold, ReAct-clean, late batches, no-signature,
  API, alert rule).

## Goal

Re-derive loops from stored spans, apply the backend's thresholds, and persist
the authoritative flag on the execution.

## Changes

1. `models.py` + alembic migration
   - `spans.call_sig` (`String(24)`, nullable; index `(execution_id, call_sig)`).
   - `executions.loop_detected` (`Boolean`, default false, indexed) +
     `executions.loop_info` (`JSONB`, nullable: `signals`, `tool_repeats`,
     `llm_repeats`, `cycle_repeats`, `cycle_steps` names — bounded, no
     payloads).
2. `attrs.py` — constants for the contract attribute names.
3. `ingest/pipeline.py`
   - Store `sdk.call.sig` on spans (`_upsert_spans`).
   - `_recompute_execution`: re-derive loop state from stored spans after each
     upsert batch — group LLM/TOOL spans by sig, count, scan ordered steps for
     signature-equal cycles (same algorithm + bounds as the SDK); apply
     `settings.loop_repeat_threshold` / `loop_cycle_repeats` /
     `loop_cycle_max_steps`; set `loop_detected` + `loop_info`.
   - `_apply_root_identity` untouched; root `sdk.loop.*` evidence is debug
     context only.
4. `config.py` — `loop_repeat_threshold: int = 3`,
   `loop_cycle_repeats: int = 3`, `loop_cycle_max_steps: int = 4`.
5. Tests (`backend/tests/`): repeat flags, cycle flags, below-threshold stays
   clean, ReAct alternation stays clean, flag survives late span batches,
   no-signature spans ignored.
