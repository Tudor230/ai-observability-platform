# 05 — Frontend: pricing admin UI

Type: task
Status: resolved
Blocked by: 01 (search/sort params on `/pricing`)
Area: audit item 6 (pricing)
Estimate: S

## Goal

Give admins a page to manage model pricing (list, add, delete) instead of
requiring curl. The backend CRUD already exists (admin-guarded, F30-safe).

## Changes

1. **Routing/nav**
   - `src/App.tsx`: lazy route `/pricing` guarded by
     `RequireRoles allow={["admin"]}`.
   - `src/components/AppShell.tsx`: nav item "Pricing" (icon: coins) in the
     admin group next to Accounts; add to `ROUTE_TITLES`.
2. **`src/api/client.ts` + `src/api/hooks.ts` + `src/api/types.ts`**
   - Types `Pricing`, `PricingInput` (provider, model, model_match, input/output
     prices, cache read/write, reasoning, currency, effective_from).
   - `pricing.list({q, sort, order})`, `pricing.create(body)`,
     `pricing.delete(id)`; `usePricing(params)` and mutation hooks invalidating
     `["pricing"]`.
3. **`src/pages/Pricing.tsx`**
   - Header with search box (API `q`, debounced) and "Add price" button.
   - Table: provider, model, match badge (`exact|prefix|default`), input/output
     per 1M, cache read/write, reasoning, currency, effective_from; sortable
     headers (provider/model/effective_from) via `SortableTh`; Delete action per
     row.
   - Add dialog: all fields (`effective_from` defaults to now, editable), numeric
     validation, USD default; success closes the dialog and refreshes the list.
   - Delete: confirm dialog; on `409` show the backend message ("referenced by
     cost records; add a newer effective-dated price instead") and keep the row.
   - Empty state: describes that unpriced models surface as "—"/no cost and
     links the "Add price" action.
   - Small hint that pricing history is immutable: corrections are new
     effective-dated rows (no edit in v1).
4. **Formatting**: use existing `formatMoney` for per-1M rates or a dedicated
   compact formatter; keep 6-decimal precision where the API returns it.

## Acceptance

- Admin sees `/pricing` in the nav, opens the page, searches (`q`), sorts, and
  sees the seeded 14 rows from the live stack.
- Adding a price for a new model makes subsequent ingest price against it
  (verified via `/costs` after a mock export or an API smoke).
- Deleting an unreferenced row works; deleting a referenced row shows the 409
  message.
- Non-admin users have no nav item and get redirected from `/pricing`.

## Tests

- Covered by ticket 16 (Pricing page RTL: list renders, add posts the body,
  delete-409 shows the message); manual run against the live backend.

## Comments

Implemented. New admin-only `/pricing` page (+ nav item, route guard, breadcrumb)
with a debounced search (`q`), sortable provider/model/effective_from headers,
the full rate table (input/output/cache read/cache write/reasoning, match
badge, effective_from), an "Add price" dialog (all `PricingIn` fields, effective
now by default) and a delete confirm that maps the 409 to the immutable-history
message. `api.pricing.list/create/remove` + `usePricing` + `Pricing`/
`PricingInput` types added; no edit in v1 (history is immutable, F30).

Evidence: `npm run lint` + `npm run build` clean, `npm test` 416 passed. Live
`/pricing` was verified against the rebuilt backend (admin key) earlier; the
RTL add/delete flow lands in ticket 16.
