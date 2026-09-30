# 03 — End-to-end verification (key-only, mismatch 409, Phoenix)

Type: task
Status: resolved
Blocked by: 01, 02

## Goal

Prove the new contract end to end against the real stack and fix the
tooling/tests that still assume a required `x-project-name`.

## Changes / checks

1. **Key-only against the backend**: run the SDK mock suite
   `uv run aiobs-mock --endpoint http://localhost:8000 --api-key <key>` (no
   `--project-id`) and verify in the `aiobs` database that executions were
   created and root spans carry `sdk.project_id` equal to the key's project.
2. **Mismatch is loud**: run with a key for project A and
   `--project-id <project B>`; verify the batch gets 409, no execution is
   written, backend logs nothing unexpected, and the SDK process continues
   normally (the OTel exporter logs a permanent export failure — the app is
   unaffected).
3. **Phoenix routing**: point the SDK at Phoenix (`:6006`) with
   `--project-id` and verify spans land in the named project via the
   `openinference.project.name` resource attribute on the pinned image
   (the `x-project-name` header only routes on Phoenix 15.5.0+); without
   `project_id`, spans land in Phoenix's default project.
4. **Tooling**: update `backend/scripts/e2e_smoke.py` and
   `backend/scripts/kpi_gate.py` invocations that pass both key and project id
   to key-only (project id only where the check is about Phoenix/routing);
   update `sdk/tests/e2e/test_phoenix_postgres.py` if it asserts on the header.
5. Confirm the deprecation warning appears exactly once per process in the
   mock CLI run and never fails a scenario.

## Acceptance

- CI (`backend`, `sdk` workflows) is green with the updated fixtures.
- KPI gate still passes: coverage, cost accuracy, and failure classification
  unchanged by the identity change.
- A documented manual check shows the 409 path and the key-only success path.

## Comments

Implemented and verified. `e2e_smoke.py` and `kpi_gate.py` now run key-only
(direct OTLP post and mock suite); the Phoenix e2e asserts the trace lands in
the `proj-1` Phoenix project.

Evidence: `kpi_gate.py` passed (KPI 1 100%, KPI 2 0.0000%, classification,
alert rules); `e2e_smoke.py` ALL OK; SDK Phoenix e2e passed with the new
routing assertion; live port check confirmed key-only ingest, root mismatch
409 (nothing stored), header conflict 409, mixed batch 200 + per-trace skip.
