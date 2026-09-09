# 03 — API client

Type: task
Status: resolved

## Question

How does the frontend call the backend?

## Answer

A typed etch client (src/api/client.ts) with per-resource query hooks
(src/api/hooks.ts). Dev server proxies /api → http://localhost:8000;
the containerized dashboard proxies /api via nginx to the backend service.
Types hand-written from the backend OpenAPI responses (src/api/types.ts);
OpenAPI codegen is future work.
