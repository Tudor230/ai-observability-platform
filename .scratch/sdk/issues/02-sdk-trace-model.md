# SDK trace model & manual API

Type: grilling
Status: resolved
Blocked by: 01

## Question

How are workflows, agents, and steps bounded and represented in the trace model — a manual API, detection, or both? What is the manual instrumentation surface (init, workflow context, custom spans, attributes)? What business-context attributes (client, project, workflow id) ride on spans, and what trace hierarchy is emitted to OTLP?

## Answer

Decided by grilling with the user.

- **Workflow boundary**: manual wrapper only for v1 — a `workflow(...)` context manager AND a `@workflow(...)` decorator, both sync and async. Teams bound workflows explicitly; the LangChain/LlamaIndex instrumentors auto-capture inner steps.
- **Trace hierarchy**: workflow root span = OpenInference `CHAIN` kind; `AGENT` spans (emitted by the instrumentors) nest under it, with LLM/TOOL/RETRIEVER/etc. under agents. Workflows can nest (child CHAIN under parent CHAIN) for multi-stage pipelines. Custom manual spans default to `CHAIN`.
- **Manual surface**:
  - `workflow(name=..., client_id=..., workflow_id=..., version=..., context={...})` — predefined attributes `client_id` / `project_id` (from init config) / `workflow_id`; `version` as a namespaced attribute; `context` as free-form JSON → OpenInference `metadata`. Span name = provided workflow name; `session.id` auto-set to `workflow_id`; `user.id` only when explicitly passed.
  - `span(name, context=...)` helper for non-framework code (validation, final response, plain API calls) — minimal surface, no kind override in v1.
- **Business context**: both — predefined namespaced attributes (`client_id`, `project_id`, `workflow_id`) for structured backend use, plus free-form `context` dict as `metadata` JSON for display.
- No OpenInference WORKFLOW kind — CHAIN root keeps conventions intact; the backend can identify workflow roots by the presence of the SDK's namespaced attributes.