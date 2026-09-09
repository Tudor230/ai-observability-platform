# 05 — Code-splitting

Type: task
Status: resolved

## Question

How is bundle size controlled?

## Answer

Pages are React.lazy-loaded under a Suspense fallback; ite.config.ts
splits endor (react/react-dom/router/query) and charts (recharts) chunks so
the initial route loads only the shell + one page chunk.
