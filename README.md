# ai-observability-platform

Observability + FinOps platform for agentic AI applications. See
[`docs/01`–`docs/05`](docs/01-problem-definition.md) for the vision and
[`plans/implementation-plan.md`](plans/implementation-plan.md) for the roadmap.

## Status

| Component | Status |
|---|---|
| **SDK** (Python; LangChain + LlamaIndex tracing, failure/usage capture, mock-workflow regression suite) | Implemented — [`sdk/`](sdk/) (see [sdk/README.md](sdk/README.md)) |
| Backend (trace processing, failure classification, cost engine) | Planned |
| Phoenix deployment + dashboard | Planned |

## Getting started (SDK)

```bash
cd sdk
uv sync --group dev
uv run pytest                      # offline regression suite
uv run aiobs-mock                  # mock-workflow pass/fail report

cd dev && docker compose up -d --wait   # Phoenix (:6006) + Postgres (:5432)
uv run aiobs-mock --endpoint http://localhost:6006
uv run python dev/inspect_traces.py     # inspect traces in Postgres
```