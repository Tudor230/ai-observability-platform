# ADR-0003: Payload handling and data retention

Status: Accepted

## Context

The platform stores traces, business metadata and (opt-in) prompt/response
payloads. docs/04 §4.9 requires data minimization and sensitive-data handling,
but the project had no documented retention or deletion story: rows lived
forever, `metadata` was persisted verbatim, and captured payloads were only
stripped at the SDK boundary.

## Decision

- **Payload capture is opt-in** (`capture_prompts=False` by default, overridable
  per workflow). Captured payload attribute keys are stripped at SDK export
  time *and* again before persistence (defense in depth).
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

- Cost/usage history and business context no longer silently accumulate PII in
  an analytics table; sensitive metadata is visibly redacted.
- Retention is an operational switch, not a schema feature: no partitioned
  tables or per-tenant TTLs yet.
- Estimated usage is visible in the data instead of being indistinguishable
  from provider-reported counts.

## Alternatives considered

- **Row-level TTL/partitioning**: more scalable but needs schema/migration work
  (deferred to production).
- **Encrypting payload columns**: keys rotation and query impact out of scope
  for the prototype; payloads are stripped instead.
- **Retention on by default**: would silently delete demo history; opted for an
  explicit env switch instead.
