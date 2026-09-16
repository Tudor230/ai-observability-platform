# 07 — AgentPrism trace viewer

Type: task
Status: resolved

## Question

How are traces visualized — build the span tree/timeline by hand or adopt a
library?

## Answer

The execution detail now renders traces with
[AgentPrism](https://github.com/evilmartians/agent-prism) (MIT, Evil Martians)
instead of the hand-rolled tree:

- **Vendored, per upstream's install model** (`npx degit`): `components/`,
  `data/` and `types/` under `src/components/agent-prism/`. `data/`+`types/`
  come from the same revision because the published npm packages lag behind
  `main`; their specifiers are aliased in `vite.config.ts` / `tsconfig.json`.
  See `src/components/agent-prism/LOCAL.md` for the three local patches.
- **Prerequisites**: React 19 (upgraded from 18; AgentPrism uses React-19 ref
  props) and Tailwind CSS 3, scoped to the vendored components. The dashboard's
  own design system stays plain CSS in `src/theme/`; the two meet at the
  `agentprism-*` tokens, remapped to the Phoenix palette in
  `src/theme/agent-prism.css` (dark + light).
- **Integration**: `src/lib/traceSpans.ts` adapts backend `Span`/`Execution`
  onto AgentPrism's `TraceSpan`/`TraceRecord` (including exposing classified
  failures under the `error.message` key its error surface reads).
  `src/components/TraceExplorer.tsx` composes the library's `TreeView`
  (+ search, expand/collapse), `DetailsView` and resizable panels into the
  Spans tab. The failures and business-context tabs stay app-owned.
- **Bundle**: the viewer (AgentPrism + Radix + lucide) rides in the lazy
  `ExecutionDetail` chunk (~122 kB raw / 40 kB gzip); Tailwind adds ~8 kB gzip
  of CSS.

Upstream's data-package test suite runs in our Vitest run (411 tests total),
plus app-side adapter tests in `src/lib/__tests__/traceSpans.test.ts`.
