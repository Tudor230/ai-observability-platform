# 04 — Analytics & alerts

Type: task
Status: resolved

## Question

How are analytics aggregated and when are alerts evaluated?

## Answer

Daily rollup (ackend/src/aiobs_backend/analytics.py) recomputes
daily_metrics across total/project/client/workflow dimensions with
execution/usage/financial metrics plus **p50/p95/p99 latency**. Alert rules
derive from budgets (warning ≥80%, critical ≥100% utilization) with
open-alert dedupe. A background loop in the app lifespan runs rollup + alert
evaluation every AIOBS_ALERT_INTERVAL_S seconds; on-demand admin endpoints
POST /api/v1/metrics/rollup and POST /api/v1/alerts/evaluate trigger the
same work immediately.
