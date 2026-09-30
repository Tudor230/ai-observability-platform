# 02 — SDK: Phoenix resource attribute + `project_id` deprecation warning

Type: task
Status: resolved
Blocked by: —

## Goal

Keep the SDK wire format compatible while making the key-only path
first-class: set the canonical `openinference.project.name` resource attribute
when the deprecated `project_id` is configured, and warn that the option is
deprecated. No config is removed. Implements ADR-0008.

## Changes

1. **`sdk/src/ai_observability/_tracing.py`** — in `build_resource` /
   `build_provider` (`:102-108`), when `config.project_id` is set, add
   `openinference.project.name = config.project_id` to the resource attributes
   (keep the existing `x-project-name` header in `build_headers`).
   Use the OpenInference semconv constant if already importable, otherwise the
   literal string; do not add a new dependency just for this.
2. **`sdk/src/ai_observability/_config.py` / `__init__.py`** — when
   `project_id` is provided explicitly or via `AI_OBSERVABILITY_PROJECT_ID`,
   emit a `DeprecationWarning` (once per process) explaining that the API key
   identifies the project and the option is Phoenix-routing-only. Respect the
   SDK isolation guarantee: a warning, never an error; `warnings.warn(...)`.
3. **`sdk/src/mock_workflows/cli.py`** — `--project-id` default becomes `None`
   (key-only invocation); keep the flag working and warn when passed
   (it is the deprecated Phoenix-routing path).
4. **Docs already updated**: `sdk/README.md`, `plans/sdk.md` §3–§5.

## Acceptance

- `init(api_key=..., project_id="p1")` → resource carries
  `openinference.project.name = "p1"` and `x-project-name` header is still sent;
  a `DeprecationWarning` is visible.
- `init(api_key=...)` (or key only) → no resource attribute, no warning, no
  behavior change; backend key-first auth accepts it.
- `init(project_id=...)` via env behaves the same as the explicit arg.
- `aiobs-mock` defaults to key-only; `--project-id` still routes in Phoenix.

## Tests

- `sdk/tests/unit/test_config.py` — env/arg deprecation warning; empty env does
  not warn.
- New `sdk/tests/unit/test_tracing_resource.py` (or extend
  `test_export_health.py`) — resource attribute present/absent,
  `build_headers` still emits the header when set.
- `sdk/tests/unit/test_export_health.py` — unchanged exporter behavior.
- Run `cd sdk && uv run pytest` and `uv run ruff check .`.

## Comments

Implemented. `build_resource` sets `openinference.project.name` from
`project_id`; `build_headers` unchanged (x-project-name when set). `init()`
emits one `DeprecationWarning` per process when `project_id` comes from an
argument or `AI_OBSERVABILITY_PROJECT_ID`. The mock CLI defaults
`--project-id` to `None`; the two scenarios that hard-asserted
`sdk.project_id == "proj-1"` now assert against the configured value (absent
when key-only), with a new `attr_absent`/`project_attr_matches_config` helper.

Evidence: `uv run pytest` 128 passed + 1 e2e; `uv run aiobs-mock` 18/18.
