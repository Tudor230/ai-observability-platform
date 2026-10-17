# Loop detection — spec

Status: implemented (2026-10-17) — demo evidence in `demo/`
Source: planning session (grilling of the loop-detection idea, 2026-10-17)

## Problem

Agents can get stuck repeating themselves (same tool call with the same
arguments, same LLM call, same multi-step pattern) without any span *erroring*.
The platform has no way to see it, alert on it, or investigate it. A looping
execution burns tokens and cost while showing as a perfectly healthy `ok`
execution.

## Settled decisions (planning session, 2026-10-17)

1. **Loop is a separate flag, not a failure kind.** `aiobs_contracts.ERROR_KINDS`
   stays about errors; a looping execution may be `ok`. The backend stores a
   loop flag + details on the execution.
2. **Detection window is one execution/trace.** No cross-execution/session
   loops in v1. HITL continuation roots are subtree-scoped like failure
   propagation, so an interrupt run and its resume run don't bleed evidence.
3. **Three signals**, all *signature-based* (threshold N = 3 by default):
   - `tool_repeat` — same tool name + same normalized-args signature ≥ N times;
   - `llm_repeat` — same model + same full-input signature ≥ N times;
   - `cycle` — a consecutive ordered pattern of 2–4 steps whose per-step
     signatures repeat ≥ N times (name-only alternation, e.g. ReAct
     agent→tools→agent, is *normal* and never flags).
4. **Inferred retries are excluded**: a span the SDK identifies as part of a
   retry chain (failed attempt → successful retry) carries no signature, so it
   cannot feed repeat counts. Retry storms stay the retry signal's job.
5. **Signatures are salted hashes, computed locally before payload stripping.**
   HMAC-SHA256 over normalized input, truncated, with a per-process random salt
   that is never exported. Prompts still never leave the SDK; only an opaque,
   run-scoped token per LLM/TOOL span (`sdk.call.sig`) is exported.
6. **Split of authority: SDK measures live, backend decides.** The SDK stamps
   triggering spans (`sdk.loop.signal`, `sdk.loop.repeat_count`) and root
   evidence counts (`sdk.loop.*`) for trace-UI visibility. The backend
   re-derives repeats and cycles from stored `sdk.call.sig` values, applies its
   own configurable thresholds, and owns `execution.loop_detected`. Backend
   wins on disagreement.
7. **Thresholds are backend config** (`loop_repeat`/`loop_cycle_repeats` = 3,
   `loop_cycle_max_steps` = 4), env-overridable; SDK detection has only an
   on/off switch (`init(loop_detection=False)` + env) and uses the contract
   default for its live marks.
8. **Alerting uses the existing rule engine**: new `loop_executions` metric
   (count of looped executions in the window), warning/critical thresholds,
   seeded built-in rule, existing dedupe/channels/60 s loop. No per-execution
   alert spam.
9. **Surfaces**: execution flag + filter in the API; executions table badge,
   filter control entry, and detail-panel section in the dashboard; alert in
   the Alerts page/notifications. No changes to error-rate/status semantics.
10. **Derived data needs an ADR note**: exporting salted signature hashes is a
    new data class; ADR-0003 (payload handling) gets an amendment, plus a new
    ADR-0014 recording the flag-not-kind and measurement/authority split.

## Non-goals

- Aborting or interrupting a looping run from the SDK (detection is passive).
- Cross-execution / session-level loop detection.
- RETRIEVER-span signatures (cycles over retrievers are rare; revisit if seen).
- Name-only cycle detection (noisy on every ReAct agent).
- Per-execution alert notifications (aggregated metric only).

## Open risks

- Attribute-shape drift across instrumentors (`input.value` vs
  `llm.input_messages.*`): extraction reads several shapes and *skips* when no
  input is present — never guesses.
- LLM repeats are rare while history grows; `tool_repeat` and `cycle` carry the
  load. Documented, not a bug.
- Legit polling tools (3 identical polls) can trip `tool_repeat`; thresholds are
  configurable and the alert is window-aggregated.
- Streaming export means a root can leave before late children (HITL resume):
  SDK root evidence may be partial, but the backend re-derivation is the
  authority, so nothing user-visible depends on it.
