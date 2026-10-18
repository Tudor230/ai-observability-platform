# 05 — SDK: drop `client_id`, debug-only `project_id`, key-only examples

Type: task
Status: resolved
Blocked by: —
Area: refinements v3, SDK (ADR-0011, ADR-0012)
Estimate: M

## Goal

The SDK stops shipping client attribution and stops presenting `project_id` as
a normal option: production integrations use the API key alone; the override
survives only for debugging/testing.

## Changes

1. **Remove `client_id`**
   - `_workflow.py`: drop the `client_id` parameter from the `workflow(...)`
     context-manager factory and the `@workflow` decorator, and drop the
     `SDK_CLIENT_ID` attribute emission. (`aiobs_contracts.SDK_CLIENT_ID` stays
     exported — no breaking contracts release.)
   - `dev/inspect_traces.py`: drop the `client_id` projection and column.
   - `src/mock_workflows/*/scenarios.py` (6 files) and
     `tests/unit/test_workflow.py`, `tests/e2e/test_phoenix_postgres.py`:
     remove `client_id` args and `sdk.client_id` assertions.
2. **`project_id` becomes debug-only**
   - Keep the option and its `x-project-name` / `openinference.project.name`
     behaviour, but make the warning and docs explicit: *debug/test routing
     only; do not use in production* (ADR-0008/ADR-0012). Warning text updated
     (still a `DeprecationWarning`-style log, no API change).
   - `init()` docstring + `sdk/README.md` gain the not-for-production note.
3. **Examples use keys only**
   - `examples/checkout_agent.py`, `rag_checkout_agent.py`,
     `rag_order_support_llamaindex.py`, `langgraph_refund_approval.py`,
     `ollama_chat.py`: remove `--client-id` and `--project-id` flags and the
     `client_id=`/`project_id=` call arguments; they take `--api-key` +
     `--endpoint` only.
   - `examples/README.md` updated accordingly, including the debug-only note.
   - `aiobs-mock` may keep `--project-id` for Phoenix inspection (tests/docs
     say so explicitly).
4. **Version** — `__version__ = "0.2.0"` (released in ticket 06).

## Acceptance

- `grep -rn client_id sdk/src` returns nothing outside comments/history.
- The mock suite and e2e pass; the mock CLI still routes to Phoenix with
  `--project-id`.
- Every example runs with `--api-key` only (offline mock mode unaffected).

## Tests

- `uv run pytest -q` and
  `uv run pytest --cov=ai_observability --cov=mock_workflows --cov-fail-under=80`.

## Comments

Done. `client_id` is gone from the `Workflow` boundary, the `workflow()`
factory, both decorator wrappers, `_build_attributes`, `_attributes`'
re-export list, `dev/inspect_traces.py` (SQL projection + column), all six mock
scenario families and their assertions, the unit/e2e tests, and both READMEs
(the PyPI long-description too). `project_id` stays in `init()`/env but is now
framed as a **debug/testing override that should not be used in production**
(warning text + docstrings updated); tests and `aiobs-mock` keep it for Phoenix
inspection. `examples/*.py` (all six, including `init_only_agent.py`) dropped
`--client-id`/`--project-id` and pass the API key + endpoint only — verified by
an AST/source check. Version bumped to `0.2.0`.

Evidence: **161 passed, 1 skipped** (e2e needs `AI_OBSERVABILITY_E2E=1`);
coverage **87.29%** (gate 80%); `uv lock --check` clean; `aiobs-mock` offline
**28/28 scenarios**; signature check confirms `client_id` is absent from
`workflow()` while `init()` still accepts the debug override and warns.
