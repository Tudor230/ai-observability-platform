## Destination

Two plan documents committed to the repo under `plans/` — kept out of `docs/`, which holds the general idea (`docs/01`–`docs/05`): a rough platform-wide plan (`plans/implementation-plan.md`) and a detailed SDK plan (`plans/sdk.md`, the focus of this effort). The map is complete when both MDs are written and every decision feeding them is resolved. Backend and frontend plans (partner's) will sit alongside in `plans/`.

## Notes

- Domain: AI observability / agentic monitoring. Read `docs/01`–`docs/05` (problem definition, process analysis, to-be solution, high-level architecture, KPIs) before deciding — they record the platform vision and the proposed Python/OTel/Phoenix stack.
- Skills: grilling + domain-modeling for grilling tickets; research for research tickets; prototype when "how should it look" is the question.
- Settled before charting (user): Python-only SDK v1; OTel + OpenInference foundation; auto-instrumentation for LangChain + LlamaIndex; SDK captures failure/usage while the backend classifies and computes cost; prompt/response capture opt-in; mock workflows included in the SDK plan.
- Plan, don't do: tickets resolve decisions feeding the MDs; the MDs are assembled by the final ticket.
- Ticket numbers map to `.scratch/sdk/issues/NN-<slug>.md`. The SDK planning effort lives here; backend/frontend planning efforts get their own `.scratch/<slug>/` maps.

## Decisions so far

<!-- the index: one line per closed ticket, enough to judge relevance, then zoom the link for the detail the ticket holds -->

- [OpenInference coverage research](issues/01-openinference-coverage.md): OpenInference has 10 span kinds and covers tokens/tools/retrieval/costs but no failure/retry attributes; stable LangChain + LlamaIndex instrumentors capture prompts, tokens, tools, errors automatically; Phoenix stores spans and computes cost server-side, classifies nothing — our SDK must add workflow boundaries, business context, namespaced failure attributes, prompt-capture gating, and its own TracerProvider/OTLP export.
- [SDK trace model & manual API](issues/02-sdk-trace-model.md): manual workflow wrapper (CM + decorator, sync/async) bounding a CHAIN-root span with nested AGENT/LLM/TOOL spans; predefined client_id/project_id/workflow_id + version attributes plus free-form context dict as metadata; session.id = workflow_id, user.id explicit; minimal `span(name, context)` helper for non-framework code; workflows nestable.
- [SDK config & export reliability](issues/03-sdk-config-export.md): `init(api_key, endpoint, project_id)` with `AI_OBSERVABILITY_*` env fallbacks; API key + project id as custom OTLP headers; OTLP HTTP transport; four isolation guarantees (never raise, never block, drop on overflow, log); OTel batch/retry defaults; atexit + explicit flush(); no sampling in v1; standard Resource attributes.
- [Failure & usage capture schema](issues/04-failure-usage-capture.md): exception events + ERROR status plus `sdk.error.type/message` attrs; raw facts + best-effort `sdk.error.kind` hints, backend classifies; token counts validated/backfilled, no `llm.cost.*` emission; SDK provider-normalization map; prompt capture global-off with per-workflow override; retries via `sdk.retry.of` (invocation params) + `sdk.retry.count` (SpanProcessor sibling-span inference); workflow root reflects failures.
- [Retry observability research](issues/09-retry-observability.md): LangChain retries surface as repeated sibling ERROR spans with `retry:attempt:N` tags the OpenInference tracer ignores; `max_retries` visible in invocation params only for Anthropic, not OpenAI; LlamaIndex retries invisible; clients expose no hooks except injected httpx event hooks — hence the SpanProcessor inference approach adopted in ticket 04.
- [LangChain instrumentation scope](issues/05-langchain-instrumentation.md): reuse `openinference-instrumentation-langchain` with our TracerProvider; v1 covers LLM/agents/tools/retrievers/prompt templates, not memory; LangGraph out of v1 scope (partial CHAIN tracing only); spans nest under the manual workflow root; AGENT reclassification hook kept small; double-instrumentation warning.
- [LlamaIndex instrumentation scope](issues/06-llamaindex-instrumentation.md): reuse `openinference-instrumentation-llama-index` (v4.x, llama-index >= 0.12.x); full component sweep (LLM, query engines/chains, retrievers, embeddings, agents, tools, rerankers); spans nest under the manual workflow root — both frameworks can mix under one root; same AGENT reclassification hook; double-instrumentation warning.
- [Mock workflows design](issues/07-mock-workflows.md): Python scenarios via framework fake models (FakeChatModel/MockLLM) with fixed usage, run through the real SDK; pytest + CLI report; programmatic assertions on trace shape, attributes, failure propagation; failure catalog incl. timeout/LLM error/invalid JSON/retrieval failure/high latency/rate limit/retry-then-success; token-count assertions now, backend-ready for cost + classification; CI acceptance gate.
- [Assemble the plan MDs](issues/08-assemble-plan-mds.md): wrote `plans/implementation-plan.md` (rough platform plan from docs 01–05 + phased roadmap) and `plans/sdk.md` (detailed SDK plan with decision index). **The map's destination is reached — no tickets remain.**

## Not yet specified

- Plain OpenAI/Anthropic client auto-instrumentation (hangs on framework-coverage gaps found by research)
- SDK packaging & distribution (PyPI, versioning) and the public package/import name (sketched as `ai_observability` in ticket 02, undecided); async/streaming support specifics
- Redaction mechanics for opt-in prompt capture
- Post-v1 frameworks (CrewAI, etc.), LangGraph first-class support, memory tracing, LangChain reranker reclassification, and non-Python SDKs
- Automated evaluation beyond mock workflows (LLM-as-judge style)
- Exact per-attempt retry counts via an opt-in httpx event-hook client
- Main-MD depth for backend/dashboard/Phoenix/alerts — deliberately rough

## Out of scope

- Building the platform itself (backend, cost engine, dashboard, Phoenix deployment, alerting) — the destination is plan docs, not the build
- The business agents being monitored; model training / fine-tuning
- Deep backend planning — the main MD only sketches it