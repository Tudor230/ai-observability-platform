# 01 — Ollama instrumentation

Type: task
Status: resolved
Blocked by: —

## Goal

Decide how raw `ollama` Python client calls become LLM spans in the SDK:
reuse an existing OpenInference instrumentor or build custom tracing.

## Decision

Reuse **`openinference-instrumentation-ollama`** (v0.1.9+, Apache-2.0, `ollama >= 0.4.0`)
with the SDK-owned TracerProvider — the same pattern as the LangChain and
LlamaIndex instrumentors; no custom tracing.

- **Coverage**: `ollama.chat`, `ollama.Client.chat`, `ollama.AsyncClient.chat`
  (sync + async, `stream=True` included) → OpenInference **LLM** spans
  (`Chat`/`AsyncChat`) with input/output messages, tool schemas,
  `llm.invocation_parameters`, `llm.provider = "ollama"` and `llm.model_name`
  recorded request-side (errored calls keep them), token counts from
  `prompt_eval_count`/`eval_count` (total derived), streaming output
  reconstructed on drain, errors as exception events + ERROR status.
- **Not covered upstream**: `generate`, `embed`/`embeddings` — documented, not
  worked around.
- **Dependency shape**: the instrumentor keeps `ollama` in its `instruments`
  extra, so the SDK adds it to the **dev** group only (tests/scenarios); the
  raw client stays optional at runtime.
- **Absent client**: `init()` skips Ollama instrumentation silently (debug log);
  instrumentation failures never propagate (plan §8).
- **No ADR**: extends the already-decided "reuse OpenInference instrumentors"
  pattern (`.scratch/sdk/issues/05`, `06`); the record lives here and in the
  plans, like the LangGraph effort.
- **Local pricing** is out of scope here and handled by ticket 05.

## Comments

Implemented via tickets 02–05. Verified against the installed wheel
(`openinference-instrumentation-ollama 0.1.9`, `ollama 0.6.3`) while writing the
offline fakes: request extractor sets `openinference.span.kind=LLM`,
`llm.provider`, `llm.model_name`, messages, invocation parameters; response
extractor sets output message, token counts, finish reason.
