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

## Comments

- 2026-10-17: the loop-detection change set landed on this branch before the
  tag, so `sdk-v0.2.0` also ships it (additive: `sdk.call.sig` / `sdk.loop.*`
  attributes, `init(loop_detection=...)`, no signature changes). Full gates
  re-run on the frozen tree: SDK 177 passed + 30/30 mock scenarios +
  `uv lock --check`; backend 178 passed; frontend 538 passed + typecheck/lint;
  `uv build` produces `ai-observability-sdk 0.2.0` and unchanged
  `aiobs-contracts 0.1.0` (satisfies `>=0.1,<0.2`). Local annotated tag
  `sdk-v0.2.0` prepared on the loop-detection tip — push it to run
  `release.yml`.
- 2026-10-17 (post-release): **sdk-v0.2.0 shipped broken for fresh installs.**
  PyPI still had `aiobs-contracts 0.1.0` (pre-loop names) and the workflow's
  `skip-existing` never uploaded the updated contracts, so
  `pip install ai-observability-sdk==0.2.0` resolved the old contracts and
  failed at import (`LOOP_CYCLE_MAX_STEPS`). Fixed by bumping
  `aiobs-contracts` to **0.1.1** (the additive bump that was missing), pinning
  the SDK to `aiobs-contracts>=0.1.1,<0.2`, and releasing
  **`sdk-v0.2.1`**; publishing 0.1.1 also repairs existing 0.2.0 installs
  (pip resolves the newest matching contracts). `release.yml` gained a
  `smoke-install` gate: after contracts are published, the built SDK wheel is
  installed in a clean venv against PyPI and imported — a mismatch now fails
  the release before the SDK is uploaded.
