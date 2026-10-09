# 17 — SDK: coverage measurement + CI floor

Type: task
Status: open
Blocked by: —
Area: audit item 12 (coverage)
Estimate: S

## Goal

Measure SDK coverage and enforce a floor in CI, completing the "80% test
coverage" goal across all three components (backend already at 86%).

## Changes

1. **`sdk/pyproject.toml`** (dev group): add `pytest-cov>=7`.
2. **Measure**: run
   `uv run pytest -q --cov=ai_observability --cov=mock_workflows --cov-report=term-missing`
   and record the baseline in this ticket's comments.
3. **CI** (`.github/workflows/sdk.yml`, unit job):
   `uv run pytest -q --cov=ai_observability --cov=mock_workflows --cov-fail-under=<floor>`.
   - If the baseline is ≥80: set `<floor>=80` immediately.
   - If below 80: add focused tests for the largest gaps (likely connector
     modules) until ≥80; if a module is genuinely not unit-testable offline
     (e.g. network paths), exclude it explicitly with a comment and set the
     floor to keep the covered scope ≥80.
4. **Docs**: one line in `sdk/README.md` Development section on the coverage
   command/floor.

## Acceptance

- CI unit job enforces the coverage floor; a deliberately uncovered branch
  lowers the number locally (sanity check).
- Coverage numbers are recorded in the comments with the excluded scope (if
  any) justified.
- No test runtime blow-up (suite stays within the 15-minute job timeout;
  currently ~22 s).

## Tests

- This ticket **is** the measurement + gate; run
  `uv run pytest -q --cov=ai_observability --cov=mock_workflows` locally and
  paste the table into the comments.

## Comments
