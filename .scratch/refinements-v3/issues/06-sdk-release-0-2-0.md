# 06 — SDK: release 0.2.0

Type: task
Status: open
Blocked by: 05
Area: refinements v3, packaging/release
Estimate: S

## Goal

Publish the breaking SDK change as `sdk-v0.2.0` through the existing
tag-triggered release workflow.

## Changes

1. Confirm `sdk/src/ai_observability/__init__.py` `__version__ == "0.2.0"` and
   that `sdk/README.md` + `CHANGELOG`-style notes (the README's own section)
   state the two breaking changes: `client_id` removed, `project_id`
   debug-only.
2. `uv lock --check` clean (the lockfile changes in this effort must be
   committed before tagging).
3. Tag and push: `git tag sdk-v0.2.0 && git push origin sdk-v0.2.0`.
4. Watch `release.yml`: build gate (offline tests + tag↔version↔contracts
   assertions) → `aiobs-contracts` publish (skip-existing, stays 0.1.0) →
   `ai-observability-sdk` 0.2.0 publish → GitHub Release.
5. Verify on PyPI that 0.2.0 is live and that the wheel metadata still pins
   `aiobs-contracts>=0.1,<0.2`.

## Acceptance

- `pip install ai-observability-sdk==0.2.0` yields an SDK whose `workflow()`
  has no `client_id` parameter and whose `init()` documents `project_id` as
  debug-only.
- PyPI 0.2.0 + GitHub Release exist; 0.1.0 remains installable.

## Tests

- `python -c "import ai_observability, inspect; assert 'client_id' not in
  inspect.signature(ai_observability.workflow).parameters"` in a fresh venv with
  the published version.
