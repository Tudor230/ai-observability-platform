# SDK config & export reliability

Type: grilling
Status: resolved
Blocked by: 01

## Question

How do teams configure the SDK (API key, endpoint, env vars, init signature)? What OTLP transport (HTTP vs gRPC), batching, and retry behavior? How is failure isolation guaranteed — observability must never break the app (exception handling, async flushing, shutdown)?

## Answer

Decided by grilling with the user.

- **Config**: `init(api_key, endpoint, project_id, ...)` with env-var fallbacks — `AI_OBSERVABILITY_API_KEY`, `AI_OBSERVABILITY_ENDPOINT`, `AI_OBSERVABILITY_PROJECT_ID`; explicit args override env. `project_id` also feeds the workflow-root attributes (ticket 02).
- **Routing/auth**: custom OTLP headers carry the API key + project id; the platform's ingest authenticates and routes by them. Works with Phoenix today, extensible to our own collector later.
- **Transport**: OTLP HTTP to `/v1/traces` (Phoenix-native). gRPC deferred.
- **Failure isolation**: all four guarantees — wrapper/instrumentor exceptions never propagate; export on background threads so the app thread never blocks on network; queue overflow drops spans with a warning (never blocks, never unbounded); export/ingest failures are logged, never raised.
- **Batching & retry**: OTel defaults — BatchSpanProcessor (5s interval, 512 spans/batch, 2048 queue) + OTel exporter retries with exponential backoff.
- **Flush**: `atexit` hook flushes pending spans for short-lived processes + explicit `flush()` API for app shutdown. Long-running servers rely on the normal batch flow.
- **Sampling**: none in v1 — mock workflows need complete, expected traces (ticket 07); rate sampling documented as future work.
- **Resource attributes**: `service.name`, `service.version`, `deployment.environment` from standard OTel env conventions (`OTEL_SERVICE_NAME`, etc.).