# ADR-0001: Backend ingests OTLP directly; SDK and backend share a contract package

Status: Accepted

## Context

The platform backend (`plans/backend.md`) must turn the SDK's telemetry into
normalized executions, classified failures, and costs. Two ingestion shapes were
considered:

1. Read spans back out of Phoenix/Postgres (Phoenix as the only source).
2. Receive OTLP directly and keep Phoenix as the canonical trace store
   (not a read dependency).

Separately, the SDK emits and the backend consumes the same attribute names
(`sdk.*`, `llm.*`, `exception.*`), the same failure taxonomy, and the same
redaction rules. Keeping those in two places invites silent drift.

## Decision

- The backend owns a direct OTLP HTTP receiver (`POST /v1/traces` and the
  standard `/v1/traces`). Processing is idempotent per `trace_id`
  (delete-and-recompute). Phoenix remains the canonical trace store/UI.
- A shared package `shared/aiobs_contracts` (`aiobs-contracts`, editable path
  dependency of both the SDK and the backend) is the single source of truth for
  attribute names, `ERROR_KINDS`, hint patterns, and payload-redaction rules.

## Consequences

- The backend has a clean, testable ingest path exercised by the KPI gate
  (`backend/scripts/kpi_gate.py`), which runs the real SDK mock suite against a
  live backend.
- SDK/backend contract drift is structurally prevented; both test suites pass
  after the extraction.
- Cost of change: the backend must decode OTLP protobuf (small, bounded) and
  both packages must depend on `aiobs-contracts` (lightweight, no heavy
  framework deps).

## Alternatives considered

- Phoenix read-back: couples the backend to Phoenix internals and delays
  processing until Phoenix flushes; not chosen.
- Copying constants into each package: zero coupling but guaranteed drift;
  explicitly rejected in favor of the shared package.