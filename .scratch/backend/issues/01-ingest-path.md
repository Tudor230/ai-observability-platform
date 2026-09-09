# 01 — Ingest path

Type: task
Status: resolved

## Question

How does the backend receive SDK telemetry: direct OTLP receive or read-back
from Phoenix/Postgres?

## Answer

Chose a **direct OTLP HTTP receiver** (POST /v1/traces, plus the standard
/v1/traces path so SDK exporters can point straight at the backend). The
backend decodes the OTLP protobuf (ExportTraceServiceRequest), validates the
SDK headers (x-project-name + uthorization: Bearer), and persists
normalized executions/spans. Phoenix remains the canonical trace store but is
not a read dependency. Re-ingesting a 	race_id fully recomputes its rows
(idempotent). Verified end-to-end: iobs-mock exports 14/14 scenarios into
the backend and the KPI gate passes (ackend/scripts/kpi_gate.py).
