# 06 — Shared contracts

Type: task
Status: resolved

## Question

How do SDK and backend stay in lockstep on attribute names and taxonomy?

## Answer

Extracted shared/aiobs_contracts (package iobs-contracts, editable path
dependency of both the SDK and the backend). It is the single source of truth
for sdk.*/OpenInference attribute names, the failure taxonomy, payload
redaction rules, and hint patterns. Both suites (59 SDK tests, backend tests)
pass after the extraction.
