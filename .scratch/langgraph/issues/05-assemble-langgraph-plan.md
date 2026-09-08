# Assemble the LangGraph plan

Type: task
Status: resolved
Blocked by: 03, 04

## Question

How do `plans/sdk.md` and `plans/implementation-plan.md` change to reflect first-class LangGraph support with automatic HITL capture?

## Answer

- **`plans/sdk.md`:**
  - §2 Scope: drop "no LangGraph first-class support" from the v1 exclusions; add a line that LangGraph traces via the LangChain instrumentor with automatic HITL capture.
  - §7.1 LangChain: replace the "LangGraph out of v1 scope / partial CHAIN / interrupt-resume unhandled" limitation with a LangGraph paragraph (nodes trace as CHAIN/AGENT under the workflow root via the LangChain instrumentor; instrumentor >= 0.1.67 handles `GraphInterrupt` as OK; SDK adds `sdk.hitl.*`).
  - New §7.x "LangGraph human-in-the-loop": the auto-interception design (`_langgraph.py` boundary patch + `GraphCallbackHandler` lifecycle hook), the `sdk.hitl.*` attribute table, control-flow exception filtering, the trace-keyed registry and root stamping, session correlation guidance (`workflow_id` = LangGraph thread id → Phoenix session), and the reliability guarantees (pass-through wrapper, exceptions never propagate).
  - §6.1 / §4 gaps: note control-flow exceptions are excluded from failure capture.
  - §9 Mock workflows: add the LangGraph scenarios to the catalog list.
  - §10 Deferred: remove "LangGraph first-class support"; keep anything else (e.g. `sdk.hitl.node` precision on old langgraph).
  - §12 Decision index: add rows for the `.scratch/langgraph/` tickets 01–05.
- **`plans/implementation-plan.md`:**
  - §8 Deferred items: remove "LangGraph first-class support"; leave the rest.
- **`sdk/README.md`:** add a LangGraph + HITL paragraph to "What the SDK emits" and the mock-scenario list.