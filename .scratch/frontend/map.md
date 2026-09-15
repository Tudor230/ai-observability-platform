# Frontend Planning Map

## Destination

`plans/frontend.md` implemented in `frontend/` — the dashboard consuming the
backend Platform API. Decision tickets below record resolved decisions.

## Notes

- Read `plans/backend.md` for the API contract; the frontend talks only to
  `/api/v1` endpoints.
- Views: engineering (trace/failure explorer), manager (cost/trend/budget),
  executive (unit economics + forecast).

## Decisions so far

- [01 — Stack & scaffold](issues/01-stack-scaffold.md): React 18 + Vite +
  TypeScript, TanStack Query, React Router, Recharts. Dark theme tokens.
- [02 — Routing & shell](issues/02-routing-shell.md): AppShell with nav,
  role switcher (Engineer / SDM / Finance), and global filters (days, project,
  client, workflow) lifted into a shared context.
- [03 — API client](issues/03-api-client.md): typed fetch client + query hooks;
  dev-server proxy `/api` → backend; production nginx proxy.
- [04 — Views](issues/04-views.md): Overview KPIs + cost trend, Engineering
  trace table + span/failure tree detail, Manager cost/trend/budget/alerts,
  Executive unit economics + linear forecast.
- [05 — Code-splitting](issues/05-code-splitting.md): lazy-loaded pages and
  vendor/charts manual chunks to keep the initial bundle small.
- [06 — Phoenix design system](issues/06-phoenix-design-system.md): the UI
  adopts the Arize Phoenix design system (tokens, shell layout, core
  components, chart theming; Geist fonts; dark default + light toggle).

## Fog / not yet specified

- Real-time streaming (polling suffices in v1); auth provider / multi-tenant
  RBAC UI; admin screens for pricing/budgets/projects; e2e (Playwright).