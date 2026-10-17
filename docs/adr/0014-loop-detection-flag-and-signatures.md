# ADR-0014: Loop detection is a flag backed by salted call signatures

Status: Accepted

## Context

An agent can get stuck repeating itself — the same tool call with the same
arguments, the same LLM input, the same multi-step pattern — without any span
ever erroring. Such an execution reads as a perfectly healthy `ok` execution
while burning tokens and cost, and the platform had no way to see it, alert on
it, or investigate it.

Detection could have lived entirely in the SDK (live, but the platform would
never know), entirely in the backend (post-hoc, but prompts/arguments are
stripped at export by default, so there is nothing to compare), or as another
failure kind (wrong: a loop is not an error, and the `ERROR_KINDS` taxonomy is
about failures).

A naive "same span name repeats" rule flags every ReAct agent:
`LLM → TOOL → LLM → TOOL` alternation is normal agent behavior, not a loop.
Only *identical inputs* prove a loop.

## Decision

- **Loop is a flag, not a failure kind.** `executions.loop_detected` plus
  `executions.loop_info` (signals, repeat counts, cycle step names) are
  separate from `status`/`root_error_kind`; error-rate analytics are unchanged.
  A looped execution may be `ok`, `error`, or anything else.
- **Three signals, all signature-based**, default threshold 3 (backend
  config):
  - `tool_repeat` — same tool name + same normalized arguments signature;
  - `llm_repeat` — same model + same full-input signature;
  - `cycle` — a consecutive pattern of 2–4 steps whose per-step signatures
    repeat. Name-only alternation never flags.
- **Detection window is one execution/trace.** No cross-execution or
  session-level loops in v1.
- **Retries are excluded.** Spans the SDK identifies as part of a retry chain
  (failed attempt → successful retry) carry no signature, so retry storms stay
  the retry signal's job and cannot masquerade as loops.
- **Signatures are salted, run-scoped hashes.** The SDK canonicalizes the call
  input (tool name + arguments; model + input messages), hashes it with
  HMAC-SHA256 under a per-process random salt, and exports only the truncated
  digest as `sdk.call.sig`. The salt is never exported, so digests cannot be
  correlated across processes or executions — they are equality tokens, not
  identifiers (ADR-0003 amendment).
- **The SDK measures live; the backend decides.** The SDK stamps triggering
  spans (`sdk.loop.signal`, `sdk.loop.repeat_count`) and workflow-root evidence
  counts (`sdk.loop.tool_repeats` / `llm_repeats` / `cycle_repeats`) for
  trace-UI visibility. The backend re-derives repeats and cycles from stored
  signatures on every ingest batch, applies its own configurable thresholds
  (`loop_repeat_threshold`, `loop_cycle_repeats`, `loop_cycle_max_steps`), and
  owns the execution flag. On disagreement, the backend wins — mirroring the
  failure-hint/taxonomy split.
- **The scan algorithm is shared** (`aiobs_contracts.scan_loop_steps`), so the
  SDK's live marks and the backend's re-derivation can never drift.
- **Alerting rides the existing rule engine**: a `loop_executions` metric
  (count of looped executions per day, scope-aware) with seeded built-in
  thresholds. No per-execution alert spam.

## Consequences

- A stuck agent is visible on the executions list (badge + filter), on the
  execution detail (signal counts, cycle step names), and in alerts — while
  remaining absent from failure-kind analytics.
- The SDK now exports derived prompt-adjacent data (a salted hash per LLM/TOOL
  call) even when `capture_prompts` is off. The hash is non-reversible,
  run-scoped, and cannot be linked across executions; the privacy posture is
  documented in the ADR-0003 amendment. `init(loop_detection=False)` (env
  `AI_OBSERVABILITY_LOOP_DETECTION`) disables signatures entirely.
- The existing SDK memory bounds hold: loop state is bounded per trace
  (distinct signatures capped, step window capped) — a long-running workflow
  cannot grow SDK memory.
- Thresholds are tunable without an SDK release; an SDK too old to emit
  signatures simply never produces backend-detected loops (no false positives).
- Cycles are structurally subsumed by repeats (each step of a 3× cycle repeats
  3×); the `cycle` signal adds shape, not sensitivity — it is reported
  alongside, and drives no separate decision.

## Alternatives considered

- **Name-only repeat/cycle detection**: no payload access needed, but flags
  every ReAct agent; rejected for precision.
- **Detection in the backend only, without exported signatures**: prompts are
  stripped at export when capture is off, so there is nothing to compare;
  relying on `capture_prompts` for loop detection would make it opt-in per
  payload policy.
- **A `loop` failure kind**: corrupts error-rate analytics (a stuck-but-ok run
  is not a failure) and overloads a taxonomy that classifies *errors*.
- **Hard abort / callback in the SDK**: v1 is passive measurement; aborting
  someone's agent from instrumentation is a behavior change applications must
  opt into, and was deliberately deferred.
- **Cross-execution / session-level loops**: needs cross-trace state and a
  different false-positive story; deferred until the within-execution signal
  proves useful.

## References

- `CONTEXT.md` — glossary (Loop flag, Call signature)
- `docs/adr/0003-retention-and-payload-handling.md` — salted-signature amendment
- `shared/aiobs_contracts` — `sdk.loop.*` names, `LoopStep`/`LoopScan`,
  `scan_loop_steps`
- `.scratch/loop-detection/spec.md` — implementation spec and tickets
- `sdk/README.md` § Loop detection, `backend/README.md`
