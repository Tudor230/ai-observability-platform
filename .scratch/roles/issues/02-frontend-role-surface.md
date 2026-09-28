# 02 — Frontend role-surface enumeration

Type: research
Status: resolved

## Question

Enumerate the frontend persona-role surface so the auth swap (08) is complete.
Find every place the persona role is read or used: `RoleContext`
(`src/state/RoleContext.tsx`), the `Role` type, `RoleSwitcher` and the
`NAV_ITEMS` `allow` arrays (`src/components/AppShell.tsx`), `RequireRole`
(`src/App.tsx`), the localStorage key `aiobs.role`, and how pages consume the
role. Also map the GET-only `src/api/client.ts` + `src/api/hooks.ts` surface,
and the dev/prod cookie implications (`vite.config.ts`, `dev/nginx.conf`).
Return `file:line` references for each.

## Answer

Full inventory captured in [research/02-frontend-role-surface.md](../research/02-frontend-role-surface.md). Highlights: persona role is read in exactly three files — `RoleContext.tsx` (type + `aiobs.role` localStorage), `AppShell.tsx` (`NAV_ITEMS` allow arrays + `RoleSwitcher`), `App.tsx` (`RequireRole`); no page reads the role. API client is GET-only with bare `fetch` (no credentials/headers), same-origin through both Vite dev and nginx prod proxies, so a cookie session needs no CORS change. No `useMutation`/`useForm`/dialog exists — net-new for the auth/registration UI.