# 06 — Phoenix design system

Type: task
Status: resolved

## Question

How does the dashboard look and feel, and which design system does it follow?

## Answer

The dashboard adopts the open-source **Arize Phoenix** design system
(`Arize-ai/phoenix`, Apache-2.0) — the same design language users already see
in the bundled Phoenix UI at `:6006` — and adapts it to this app's views.

- **Tokens**: `frontend/src/theme/tokens.css` ports Phoenix's design tokens —
  the 8px dimension scale, the gray/color ramps with `-rgb` companions,
  semantic aliases (`info`/`danger`/`success`/`warning`/`severe`), text
  opacities, rounding, table/badge/card/field/button/chart tokens, and the
  z-index bands. Dark is the default theme; the light palette lives under
  `.theme--light` and is toggleable (persisted in `localStorage`).
- **Type**: Geist Sans / Geist Mono, self-hosted via `@fontsource` so the
  dashboard works offline.
- **Layout**: Phoenix's shell — collapsible left side nav (52px collapsed /
  260px expanded) with brand, section separators and a footer theme toggle,
  plus a top nav with breadcrumbs, open-alert counter and persona select.
  Pages are `page` + `page-header` + grid, with a shared filter toolbar.
- **Components**: `frontend/src/components/core/` mirrors Phoenix primitives —
  `Card` (46px header), `Badge` (LCH-derived variants), `Table` (sticky 37px
  header, row borders, hover/selected states), `Tabs`, `Button`, `Alert`,
  `Field`/`Select`, `Progress`, `Metric`, `Skeleton` (loading states never
  shift layout) and an inline stroke icon set.
- **Charts**: Recharts reads Phoenix chart tokens (solid low-opacity gridlines,
  quiet axes, themed tooltip panel) resolved from CSS variables per theme;
  breakdown lists use horizontal bars rather than a second chart type.

Deliberate deviations: plain CSS classes (BEM, per Phoenix's `bem.md`
convention) instead of Emotion; no Relay/GraphQL (the backend Platform API is
REST); the role switcher replaces Phoenix's project picker.
