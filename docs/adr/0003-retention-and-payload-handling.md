# ADR-0003: Payload handling and data retention

Status: Accepted

## Context

The platform stores traces, business metadata and (opt-in) prompt/response
payloads. docs/04 §4.9 requires data minimization and sensitive-data handling,
but the project had no documented retention or deletion story: rows lived
forever, and `metadata` was persisted verbatim. Captured payloads were
stripped at the SDK boundary and again before persistence, which made the
span-detail view useless — the platform never had input/output anywhere.
Full-fidelity storage with opt-in capture and retention-based erasure
balances §4.9 against a usable debugging surface.

## Decision

- **Payload capture is opt-in** (`capture_prompts=False` by default, overridable
  per workflow). The SDK strips captured payload keys at export time when
  capture is off; when capture is on, attributes ride the OTLP stream and the
  backend persists **all** span attributes as-is (payload keys included) in
  `spans.attributes` (JSONB). The backend is the full-fidelity store; the
  dashboard can render per-span input/output from it.
- **Business metadata is redacted** before storage: values whose keys look
  sensitive (`password`, `secret`, `token`, `api_key`, `authorization`,
  `credential`, `ssn`, credit-card) are replaced with `[redacted]`,
  recursively. The rules live in `aiobs_contracts.redact_metadata` (shared).
- **Inferred token counts are flagged** with `sdk.tokens.estimated` so cost
  views can distinguish reported usage from estimates.
- **Retention is opt-in**: `AIOBS_RETENTION_DAYS=0` (default) keeps data;
  when set, `POST /api/v1/maintenance/purge` (or
  `scripts/purge_retention.py`) deletes executions, spans, cost records, daily
  metrics and alerts older than the window. Dimension rows (clients, workflows,
  agents) are retained as attribution history.
- **Deletion/erasure**: purging a window is the supported erasure mechanism;
  operators can scope it by running the purge against a database copy with a
  shorter window if needed.

## Consequences

- The analytics DB is the full-fidelity trace store: captured prompts/responses
  are queryable per span, which makes the dashboard's span detail useful for
  debugging. Operators choosing capture on must accept prompt data at rest;
  retention/purge below is the erasure mechanism.
- Sensitive metadata is visibly redacted in `executions.metadata_json`.
- Retention is an operational switch, not a schema feature: no partitioned
  tables or per-tenant TTLs yet.
- Estimated usage is visible in the data instead of being indistinguishable
  from provider-reported counts.

## Alternatives considered

- **Row-level TTL/partitioning**: more scalable but needs schema/migration work
  (deferred to production).
- **Stripping payloads before persistence (previous behavior)**: minimized PII
  at rest but made the span detail view useless (no input/output anywhere in
  the platform); replaced by full-fidelity storage with opt-in capture and
  retention-based erasure.
- **Encrypting payload columns**: keys rotation and query impact out of scope
  for the prototype; payloads are stored unencrypted at rest in dev.
- **Retention on by default**: would silently delete demo history; opted for an
  explicit env switch instead.
