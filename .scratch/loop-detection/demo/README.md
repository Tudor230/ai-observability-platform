# Loop detection — demo evidence

Captured 2026-10-17 against the docker-compose stack (dashboard `:8080`,
backend `:8000`, project **Loop Demo**), after exporting the SDK mock
scenarios over OTLP:

```bash
# one clean alternation + five stuck agents (to cross the seeded rule's
# warning threshold of 5 looped executions/day)
uv run aiobs-mock --scenario loop_clean_react \
    --endpoint http://localhost:8000 --api-key <project-key>
for i in 1 2 3 4 5; do
  uv run aiobs-mock --scenario loop_tool_repeat \
      --endpoint http://localhost:8000 --api-key <project-key>
done
```

Verified via API as well:

- `GET /api/v1/executions?loop=true` → 5 executions, each `status: ok` with
  `loop_info.signals = [tool_repeat, llm_repeat, cycle]`, counts `3/3/3`,
  `cycle_steps = [lookup_stock, ScriptedChatModel]`.
- `GET /api/v1/executions?loop=false` → the clean ReAct run, `loop: false`.
- `POST /api/v1/alerts/evaluate` → warning:
  `Looped executions: 5 looped executions today exceeds 5 looped executions
  (all projects, …)`.

Screenshots:

| File | Shows |
|---|---|
| `01-engineering-list.png` | Loop badges on `ok` executions in the Engineering table |
| `02-engineering-looped-filter.png` | "Looped only" filter → 5 in range, all badged |
| `03-execution-detail-loop-panel.png` | Loop panel: 3× same tool call / 3× same LLM call / 3× cycle steps |
| `04-alerts-looped-executions.png` | The seeded `loop_executions` warning in Alerts |
