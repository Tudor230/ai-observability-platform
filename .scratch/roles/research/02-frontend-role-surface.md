# Research 02 — Frontend role-surface enumeration

Resolves [02 — Frontend role-surface enumeration](../issues/02-frontend-role-surface.md).

## Persona role usage — only 3 files

### `src/state/RoleContext.tsx`
- `Role = "all" | "engineer" | "manager" | "executive"` (`:9`); localStorage key `aiobs.role` (`:11`).
- `initialRole()` (`:18-24`) reads localStorage, accepts only engineer/manager/executive, else `"all"`.
- `RoleProvider` (`:26-35`) writes on set (`:30`); `useRole()` (`:37-39`).
- No `client` role; client-side only, never sent to the API.

### `src/components/AppShell.tsx`
- `NavItem.allow: Role[]` (`:24`); `NAV_ITEMS` (`:28-40`): Overview `["all","engineer","manager","executive"]` (`:33`), Engineering `["all","engineer"]` (`:36`), Manager `["all","manager"]` (`:38`), Executive `["all","executive"]` (`:39`).
- `SideNav` gets `role` prop (`:82,105`); nav gate `item.allow.includes(role)` (`:122`).
- `RoleSwitcher` (`:223-238`): `<Select>` bound to `setRole`; labels All views / Engineer / SDM / Finance.
- Breadcrumbs (`:42-60`) are pathname-only, don't read role.
- Other `role=` strings are ARIA attributes — not the persona role.

### `src/App.tsx`
- `RequireRole({ allow })` (`:29-33`): `if (!allow.includes(role)) return <Navigate to="/" replace />`.
- Provider nesting (`:37-40`): `ThemeProvider > RoleProvider > FiltersProvider > Suspense > Routes`.
- Routes: `/` Overview ungated (`:43`); `/engineering` + `/engineering/:id` `allow=["all","engineer"]` (`:47,55`); `/manager` `allow=["all","manager"]` (`:63`); `/executive` `allow=["all","executive"]` (`:71`).

No page component reads the role; pages are scoped purely by route/nav gating.

## API layer (all GET, no credentials)

- `src/api/client.ts`: `BASE = VITE_API_BASE || "/api/v1"` (`:3`); single `get<T>(path)` with bare `fetch(url)` — no method/credentials/headers (`:5-11`); `qs`/`filterQuery` (`:13-24`); 12 methods `overview, executions, execution, spans, failures, workflows, clients, agents, costs, metrics, alerts, budgetStatus` (`:31-47`). Non-2xx → `Error("<status>: <body>")`, no 401/403 special-casing.
- `src/api/hooks.ts`: 12 TanStack hooks, query keys `["overview", f]` etc.; `enabled: !!id` for detail hooks (`:23,31,39`).
- `src/api/types.ts`: `Filters` (`:155-160`), `Overview`, `Execution`, `Span`, `FailureNode/Tree`, `AggregateRow`, `DayMetric`, `BudgetStatus`, `Alert`. No auth/session/user types.
- `main.tsx:23-25`: `refetchOnWindowFocus: false`, `staleTime: 15_000`; only invalidation via `RefreshButton` (`:8,17`).

## Networking / cookies

- Dev: `vite.config.ts:20-28` proxies `/api` → `localhost:8000`, `changeOrigin: true` — same-origin in browser.
- Prod: `dev/nginx.conf:15-20` proxies `/api/` → backend; SPA on `:80` — same-origin too.
- **No fetch passes credentials/cookies/auth headers today.** Default `credentials: "same-origin"` would carry cookies over the proxy, but none are set today. No CORS changes expected for a cookie-based session through the proxy.

## Form / mutation primitives (gaps for 08/09)

- **No `useMutation`, no `useForm`, no `<form>`, no dialog/modal anywhere.** First mutations + forms are net-new.
- Existing core primitives (all re-exported via `core/index.ts:1-11`): `Field`/`TextInput`/`Select` (`Inputs.tsx:3-28` — no password/email variants), `Button` (`Button.tsx:10-28`, variants default|primary|quiet|danger), `Badge`, `Card`/`CardHeader`/`CardBody`/`CardPanel`, `Table`+`Th/Td/Tr/TableEmpty`, `Tabs`, `Alert`/`QueryError`/`Skeleton`/`EmptyState`, `Metric`/`Delta`/`Progress`, 29 icons (`icons.tsx:28-238`).
- Radix deps present: `@radix-ui/react-collapsible`, `@radix-ui/react-tabs` — **no dialog primitive**.

## Facts relevant to the swap

- localStorage keys in use: `aiobs.role`, `aiobs.theme`, `aiobs.sidebar`, `aiobs.trace-explorer`.
- Role-string mapping: frontend `"all"` is a switch position (not an identity); `manager`→backend `sdm`, `executive`→backend `finance`; backend also has `admin`, future `client`.
- Ungated surface: `/` Overview not wrapped in `RequireRole`; alerts links to `/manager` from Overview/AppShell assume manager reachability — a role mismatch redirect to `/` could strand a user with dead links.