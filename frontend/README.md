# ai-observability-dashboard

Web dashboard (phase 3). Implements
[`plans/frontend.md`](../plans/frontend.md): engineering / manager / executive
views over the [backend Platform API](../plans/backend.md).

Stack: React + Vite + TypeScript, TanStack Query, React Router, Recharts.

## Development

```bash
npm install
npm run dev          # http://localhost:5173 (proxies /api to :8000)
```

Point `VITE_API_BASE` at the backend if not using the dev proxy
(e.g. `VITE_API_BASE=http://localhost:8000/api/v1 npm run dev`).

```bash
npm run build        # typecheck + production build
```

## Layout

```
src/api/        typed client + TanStack Query hooks
src/components/ AppShell, KpiCard
src/pages/      Overview, Engineering (+ ExecutionDetail), Manager, Executive
src/state/      global filters context
```