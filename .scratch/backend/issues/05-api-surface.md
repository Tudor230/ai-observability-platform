# 05 — API surface

Type: task
Status: resolved

## Question

What is the read/write API surface and how is it protected?

## Answer

/api/v1 read endpoints (overview, executions, workflows, clients, agents,
costs, metrics, alerts, budgets/status) are open in v1 but accept an optional
x-project-name header that restricts results to that project (project scope
gating). Mutating endpoints (pricing, budgets, projects, maintenance) require
x-admin-key. Ingest requires SDK headers with a valid project API key. Read
model serialization in ackend/src/aiobs_backend/api/serialize.py.
