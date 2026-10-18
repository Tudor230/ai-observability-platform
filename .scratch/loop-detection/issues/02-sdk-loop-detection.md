# 02 — SDK: call signatures + live loop measurement

Type: task
Status: resolved
Blocked by: 01
Area: loop detection, SDK
Estimate: L

## Comments

- 2026-10-17: `_signature.py` (HMAC-SHA256 of canonicalized input under a
  per-process random salt, truncated to 16 hex; `None` when no usable input),
  live measurement in `_enrichment.py` (bounded `sig_counts` + 64-step window,
  retries/failed calls excluded, subtree-scoped root evidence), and the
  `loop_detection` init/env switch are in. 16 unit tests in
  `tests/unit/test_loops.py`; scenarios `loop_tool_repeat` + `loop_clean_react`
  run in the mock suite (`aiobs-mock`: 30/30).

## Goal

Measure loops live, content-free: hash LLM/TOOL inputs, count repeats and
signature-equal cycles per trace, mark triggering spans, stamp root evidence.
Never export prompt content or the salt.

## Changes

1. New `sdk/src/ai_observability/_signature.py`
   - `call_signature(attributes) -> str | None`:
     - TOOL: `tool.name` + (`tool.parameters` or `input.value`).
     - LLM: model/provider + full input (`input.value`, else
       `llm.input_messages.*` re-joined); sorted-key JSON normalization.
     - HMAC-SHA256(canonical, per-process random key), truncated hex.
     - Returns `None` when no usable input (span skips detection, no guess).
   - Per-process key via `secrets.token_bytes`; never exported.
2. `_enrichment.py`
   - `_SpanMeta.call_sig`; `_TraceState` gains bounded `sig_counts`
     (distinct signatures capped, oldest evicted) and a bounded recent-steps
     window `(kind, name, sig)` for cycle scans (cap ~50 steps).
   - Accounting in pass 1 *after* retry enrichment: spans with inferred
     `retry_count >= 1` get no signature. On trip (count == threshold): stamp
     `sdk.loop.signal` + `sdk.loop.repeat_count` on the triggering span.
   - Cycle scan on the step window: consecutive suffix pattern lengths 2–4,
     repeats >= 3; stamp `cycle` signal likewise.
   - Root evidence: when a workflow root passes through, stamp
     `sdk.loop.tool_repeats` / `llm_repeats` / `cycle_repeats` (max observed)
     scoped to the root's subtree, like `_propagate_root_failure`.
3. `_config.py` — `loop_detection: bool = True` init kwarg + env
   `AI_OBSERVABILITY_LOOP_DETECTION`; off = no signatures at all.
4. Re-export public names in `_attributes.py` as needed (import from contracts).
5. Tests (`sdk/tests/unit/`): signature normalization + shapes; repeat trip;
   cycle trip (ReAct alternation must NOT trip); retry exclusion; off switch;
   root stamps; bounds (eviction) preserved.
6. `sdk/src/mock_workflows/`: one scenario that loops (same tool call 3×) with
   assertions on the emitted attributes.
