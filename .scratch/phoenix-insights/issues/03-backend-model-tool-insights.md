# 03 — Backend: `GET /models` and `GET /tools` insight endpoints

Type: task
Status: resolved
Area: phoenix insights, read API
Estimate: M

## Goal

Serve the two Phoenix panels our data model can already answer but no endpoint
exposes: per-model economics (`Model Insights`) and per-tool reliability
(`Tool Insights`).

## Changes

1. **`api/routes/models.py`** — `GET /models` with `start/end/days/project_id/
   workflow`; rows: `key` (`provider:model`), `provider`, `model`, `calls`,
   `executions`, `failed_calls`, `error_rate`, `total_cost`, `input_tokens`,
   `output_tokens`, `total_tokens`, `avg_duration_ms`, `p95_duration_ms`,
   `last_seen`. Cost/tokens aggregate `cost_records`; calls/errors/latency
   aggregate LLM spans; both keyed by `provider:model` and merged. Sorted by
   cost desc, then calls desc.
2. **`api/routes/tools.py`** — `GET /tools` with the same filters; rows:
   `name`, `calls`, `executions`, `failed_calls`, `error_rate`,
   `avg_duration_ms`, `p95_duration_ms`, `last_seen`; grouped by
   `spans.tool_name` (fallback `spans.name`), sorted by calls desc.
3. **Access** — both `require_access("engineer", "manager", "client")` like
   `/agents`; `resolve_project_filter` scoping; `total_cost` stripped for
   callers without cost visibility.
4. **`main.py`** — register both routers.
5. **Tests** — `tests/test_model_insights.py`, `tests/test_tool_insights.py`:
   aggregation correctness (cost from billing records, tokens, per-model
   latency), tool grouping/error rate, project scoping, client cost stripping,
   and the empty window.

## Acceptance

- A window with LLM spans and pricing yields one row per provider·model with
  cost, tokens, calls, error rate and p95 latency.
- Tool spans group by tool name; failed calls drive `error_rate`.
- Scoped callers only see their projects; client callers see no `total_cost`.

## Tests

- `uv run pytest`, `uv run ruff check .`, `uv run mypy src`.

## Result

- `GET /models` merges billing `cost_records` (cost + input/output tokens) with
  LLM spans (calls, failures, latency) on the `provider:model` key; every row
  now carries tokens and cost, which `/costs?dimension=model` alone could not.
- `GET /tools` groups TOOL spans by `spans.tool_name` (span-name fallback).
- Both are scope-aware (`resolve_project_filter`), support
  `start/end/days/project_id/workflow`, gate on
  `require_access("engineer", "manager", "client")`, and strip `total_cost` for
  client callers.
- Evidence: 156 backend tests pass (+9: aggregation, project scoping via
  team-scoped user keys, client cost stripping, empty window), `ruff check`
  clean, `mypy src` clean, coverage 88.99%.

Note: the Bearer project key is an *ingest* credential — read-scope tests use
`x-api-key` user keys with team-scoped memberships.
