# ai-observability-dashboard

Web dashboard (phase 3). Implements
[`plans/frontend.md`](../plans/frontend.md): engineering / manager / executive
views over the [backend Platform API](../plans/backend.md).

Stack: React 19 + Vite + TypeScript, TanStack Query, React Router, Recharts,
styled with the [Arize Phoenix](https://github.com/Arize-ai/phoenix) design
system (Apache-2.0); traces render with
[AgentPrism](https://github.com/evilmartians/agent-prism) (MIT).

## Development

```bash
npm install
npm run dev          # http://localhost:5173 (proxies /api to :8000)
```

Point `VITE_API_BASE` at the backend if not using the dev proxy
(e.g. `VITE_API_BASE=http://localhost:8000/api/v1 npm run dev`).

```bash
npm run build        # typecheck + production build
npm run lint
npm test
```

## Layout

```
src/api/          typed client + TanStack Query hooks
src/theme/        Phoenix design tokens (dark + light), base styles, component CSS
src/components/
  core/           Card, Badge, Table, Tabs, Button, Alert, Metric, ... + icons
  charts/         Recharts trend charts + breakdown bars
  agent-prism/    vendored AgentPrism UI/data/types (see its LOCAL.md)
  TraceExplorer   AgentPrism tree + span details for the execution page
  AppShell.tsx    side nav, top nav, breadcrumbs
src/pages/        Overview, Engineering (+ ExecutionDetail), Manager, Executive
src/state/        filters, role and theme contexts
src/lib/          formatting, forecast, chart theming, span→AgentPrism adapter
```

## Design system

The UI mirrors Phoenix's tokens and primitives (see
`.scratch/frontend/issues/06-phoenix-design-system.md`):

- tokens live in `src/theme/tokens.css`; dark is the default theme,
  `.theme--light` is toggled from the sidebar and persisted
- Geist Sans / Geist Mono are self-hosted via `@fontsource`
- charts resolve their colors from the chart tokens per theme
  (`src/lib/chartTheme.ts`)
- class naming follows Phoenix's BEM convention (`block__element`,
  `data-*` for state)

## Traces (AgentPrism)

`src/pages/ExecutionDetail.tsx` renders spans with the vendored AgentPrism
components (see `.scratch/frontend/issues/07-agent-prism-traces.md`):

- `src/components/agent-prism/` is vendored with `npx degit`; keep local edits
  to the three documented patches in its `LOCAL.md`
- `src/lib/traceSpans.ts` maps backend spans onto AgentPrism's `TraceSpan`
- Tailwind is scoped to those components; the Phoenix palette is mapped onto
  the `agentprism-*` tokens in `src/theme/agent-prism.css` (dark + light)
