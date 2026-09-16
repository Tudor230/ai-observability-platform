# Vendored AgentPrism

`components/`, `data/` and `types/` are vendored from
[`evilmartians/agent-prism`](https://github.com/evilmartians/agent-prism)
(MIT), following the library's copy-in install model:

```bash
npx degit evilmartians/agent-prism/packages/ui/src/components src/components/agent-prism
npx degit evilmartians/agent-prism/packages/data/src        src/components/agent-prism/data
npx degit evilmartians/agent-prism/packages/types/src       src/components/agent-prism/types
```

`data/` and `types/` are vendored from the same revision because the published
`@evilmartians/agent-prism-{data,types}` packages lag behind `main` and lack the
error-surface APIs the UI components use. The published specifiers are aliased
to the vendored sources in `vite.config.ts` and `tsconfig.json`.

## Local patches

1. `theme/index.ts` — `token()` returns `rgb(var(--agentprism-x) / <alpha>)`
   instead of `oklch(...)` so the tokens can carry RGB triplets.
2. `DetailsView/DetailsViewJsonOutput.tsx` — the four inline
   `oklch(var(--agentprism-code-*))` styles use `rgb(...)` for the same reason.

Both exist so the tokens can be remapped onto the Phoenix palette in
`src/theme/agent-prism.css` (dark + light), instead of shipping the library's
own Tailwind palette.
