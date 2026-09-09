# 02 — Failure taxonomy

Type: task
Status: resolved

## Question

Where does the failure taxonomy live and how are SDK hints handled?

## Answer

Authoritative taxonomy lives in the shared iobs_contracts package
(ERROR_KINDS). The backend (ackend/src/aiobs_backend/classify.py) trusts
the SDK's sdk.error.kind hint but **refines** it from raw exception text:
specific kinds (rate_limit, timeout, invalid_output, validation_error) beat
generic layer kinds (tool/provider/retrieval error). Span-level kinds are
authoritative; the execution root carries the earliest failing span's kind
(outer CHAIN wrappers classify as usiness_logic when they have no lower-layer
cause). KPI gate asserts ate_limit, etrieval_error, invalid_output
appear across the mock failure scenarios.
