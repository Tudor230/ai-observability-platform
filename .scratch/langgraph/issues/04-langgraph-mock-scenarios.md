# LangGraph mock scenarios

Type: task
Status: resolved
Blocked by: 01, 02

## Question

What deterministic mock-workflow scenarios should prove LangGraph + HITL capture end-to-end through the real SDK, and how are they wired into the regression suite?

## Answer

Add `langgraph>=1.1.9` to the `dev` dependency group in `sdk/pyproject.toml`, and a new `mock_workflows/langgraph/` package with:

- `fakes.py` — nothing new needed beyond a tiny reusable `_State` TypedDict and node helpers (the langchain `ScriptedChatModel` fakes are reused where a node calls an LLM); graphs are deterministic and offline (no network).
- `scenarios.py` — four `Scenario` entries run through the real SDK + LangChain instrumentor:
  - `lg_basic` — a linear `node_a → node_b` graph under a `workflow()` root; assert node `CHAIN` spans exist and are descendants of the root, each carrying `metadata.langgraph_node` (`node_a`/`node_b`) in its `metadata` JSON, and the root is OK.
  - `lg_hitl_interrupt` — a graph with an `interrupt({...})` node, compiled with an `InMemorySaver` checkpointer, invoked under `workflow(workflow_id="thread-1", capture_prompts=True)` with `config={"configurable": {"thread_id": "thread-1"}}`; assert the root stays **OK**, `sdk.hitl.interrupted="true"`, `sdk.hitl.interrupt_payload` parses to the expected payload, `sdk.hitl.thread_id="thread-1"`, no `sdk.error.*` on the root or interrupting node, and (best-effort) `sdk.hitl.node`.
  - `lg_hitl_resume` — same thread resumed with `graph.invoke(Command(resume=...), config=...)` under `workflow(workflow_id="thread-1")`; assert the root is OK, `sdk.hitl.interrupted="false"`, `sdk.hitl.resume_value` parses to the resume value, `sdk.hitl.thread_id="thread-1"`, and `session.id` matches the interrupt run (thread correlation).
  - `lg_hitl_stream` — drive `graph.stream(...)` for the interrupting graph; assert the interrupt payload + `interrupted="true"` are captured (exercises the lifecycle-hook path for streaming).
- `runner.py` — import `LANGGRAPH_SCENARIOS` and append to `SCENARIOS`; `mock_workflows/__init__.py` exports it.
- Assertions use `ScenarioAssertions` (kind/name/attr/status/parent helpers); payload JSON is compared via `json.loads`.

The scenario suite (`tests/scenarios/test_scenarios.py`) picks the new scenarios up automatically via the parametrized `SCENARIOS` list, so they run in CI and under `uv run aiobs-mock`.