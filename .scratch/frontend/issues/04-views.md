# 04 — Views

Type: task
Status: resolved

## Question

What does each role view show?

## Answer

- Overview: top-line KPIs (cost, executions, error rate, tokens, P95 latency)
  with period deltas + cost-over-time area chart.
- Engineering: trace explorer table → execution detail with span tree,
  failure tree, business context, token/cost/latency KPIs.
- Manager: cost by workflow/client charts, workflow & client tables, open
  alerts, budget utilization bars, consumption trend.
- Executive: total cost / cost per execution / cost per 1k tokens, cost by
  client and model, cost trend + linear 7-day forecast.
