# ADR-0005: Manual-vs-agent cost comparison is out of scope for the prototype

Status: Accepted

## Context

docs/01 §1.1/§1.4 and docs/03 §3.13 motivate the platform with cost **vs the
manual process** and "potential margin" (revenue minus AI + manual cost). The
implemented system attributes and forecasts *AI* cost only: executions carry
tokens/cost, clients/workflows/teams are the attribution dimensions, and the
Executive view answers "what did AI cost and where is it going?".

A real manual-vs-agent comparison needs data the platform does not capture:
what a human would have cost per task (salary/rate), what the task is worth
(revenue or value per client/service), and how many units were handled — i.e.
business data owned by the customer, not telemetry. Inventing defaults for
these would produce a margin number that looks authoritative but is fiction.

## Decision

- **Descope margin/manual-cost comparison for the prototype.** The documents
  remain the long-term vision; the implementation documents this gap instead of
  faking a number.
- The attribution dimensions and unit-economics metrics that *are* defensible
  ship now: total cost, cost per execution, cost per 1k tokens, cost per client
  ("service"), per model, and a 7-day cost forecast (all labeled estimates).
- A future implementation would add (per client/workflow): `manual_cost_per_unit`
  and `revenue_per_unit` inputs via the admin API, then expose
  `margin = revenue − ai_cost − manual_cost` in the Executive view. The schema
  slot exists conceptually in the attribution dimensions; no telemetry change is
  required.

## Consequences

- The Executive view does not claim margin/ROI it cannot compute.
- Reviewers can see exactly which inputs are missing and where they would plug
  in, rather than reverse-engineering a hard-coded assumption.
- If the product decision is "pursue margin", the work is additive: two
  configuration tables + one KPI, no pipeline changes.

## Alternatives considered

- **Hard-coded "manual cost = X × AI cost" heuristics**: rejected — produces
  meaningless margin numbers.
- **Adding a revenue field to workflow metadata**: possible, but without a
  product decision on semantics (per execution? per client-month?) it would be
  another fake metric.
