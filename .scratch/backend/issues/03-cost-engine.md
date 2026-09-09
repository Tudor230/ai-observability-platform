# 03 — Cost engine

Type: task
Status: resolved

## Question

How is cost computed and how are unpriced/partial-priced models handled?

## Answer

ackend/src/aiobs_backend/cost.py mirrors Phoenix pricing: resolution chain
**exact model → model prefix → provider default → unpriced**. Unpriced LLM
spans produce NULL cost (visible as "unpriced"), never 0.0. Cache-read,
cache-write, and reasoning tokens are parsed from
llm.token_count.prompt_details.* / completion_details.reasoning and priced
with their dedicated rates. Covered by ackend/tests/test_pricing.py.
