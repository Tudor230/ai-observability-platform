# 16 — Frontend: page/route tests + ratchet the 80% coverage gate

Type: task
Status: open
Blocked by: 14
Area: audit item 12 (coverage)
Estimate: L

## Goal

Cover every route/page with integration-level RTL tests (mocked API) so the
non-vendor app code reaches the 80% coverage target, then ratchet the CI gate
from the ticket 14 baseline to 80%.

## Changes (tests to add)

1. **`App.tsx` routing**
   - `RequireAuth` redirects to `/login` when unauthenticated; `RequireRoles`
     redirects home for a disallowed role (e.g. engineer on `/executive`);
     nav items filtered by role.
2. **Pages** (mocked `api` module + `renderWithProviders`):
   - `Login`: submit → `auth.login` called; error message on failure; return-to
     redirect.
   - `Overview`: KPIs render; cost hidden when `costVisible=false`; error
     banner on failure; new trend panels from ticket 10 present.
   - `Engineering`: list renders; status filter; search debounce calls the API
     with `q`; sort header click sends `sort/order`; pagination next/prev
     (ticket 13); empty state.
   - `ExecutionDetail`: spans/failure tabs by role; 404 vs failure messaging;
     cost/pricing badge logic.
   - `Manager`: costs/workflows/clients/agents tables; budgets create/edit/
     delete flow (ticket 04) with mocked API; alerts list; error banner.
   - `Executive`: KPIs + forecast chart + model table/chart (ticket 11).
   - `Client`: no cost fields anywhere (assert absence), workflow drill-down
     renders failure kinds.
   - `Projects` + `Project`: list, key add/rotate/revoke flows, read-only for
     clients.
   - `Requests`: submit (self-approval message), approve, reject modal requires
     a reason, cancel.
   - `Accounts`: create account reveals password, grant/revoke membership
     dialog, enable/disable.
   - `Pricing` (ticket 05): list/search/sort, add posts the right body,
     delete-409 message.
   - `Alerts` (ticket 09): role-based tabs, ack flow, rule dialog validation.
3. **Coverage gate**
   - After the suite is green locally, set
     `coverage.thresholds.lines/statements/functions = 80` (statements may start
     at the measured value if a gap remains; document the exception in the
     comments) and remove the ticket 14 baseline override.
   - `.github/workflows/frontend.yml` keeps `npm run test:coverage` as the gate.
4. **Flake control**
   - Deterministic dates (`vi.setSystemTime`), stable selectors
     (`getByRole`/`getByLabelText`), no reliance on animation timing.

## Acceptance

- `npm run test:coverage` reports **≥80% lines/statements/functions** on the
  non-vendor `src/**` scope, and CI fails below it.
- Every route has at least a smoke test (renders the page's title without
  errors with mocked data).
- The critical flows (login, key management, requests approvals, budgets CRUD,
  alerts ack, pricing add) have interaction tests.
- The full frontend suite passes reliably twice in a row locally.

## Tests

- This ticket **is** the tests + gate change. Record final coverage numbers in
  the comments, including any directory below target and why.

## Comments
