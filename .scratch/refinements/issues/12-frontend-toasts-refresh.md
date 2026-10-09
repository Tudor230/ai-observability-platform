# 12 — Frontend: global toasts + auto-refresh intervals

Type: task
Status: open
Blocked by: —
Area: audit item 11 (UX)
Estimate: M

## Goal

Give mutations clear, consistent feedback (toasts) and let dashboards
auto-refresh at a chosen cadence, both global and lightweight.

## Changes

1. **Toast system** (`src/components/core/Toast.tsx` + `Feedback.tsx` or new)
   - `ToastProvider` mounted in `App.tsx`; `useToast()` API:
     `toast.success(message)`, `toast.error(message)`, `toast.info(message)`.
   - Stacked bottom-right (top-center on mobile), auto-dismiss ~4 s,
     dismiss button, `role="status"`/`aria-live="polite"`, variants using the
     existing `Alert` styling; cap the stack (e.g. 4).
   - Export from `components/core/index.ts`.
2. **Wire mutations** — replace/keep inline errors but add success + failure
   toasts for:
   - Project keys add/rotate/revoke (`pages/Project.tsx`);
   - Requests submit/approve/reject/cancel (`pages/Requests.tsx`);
   - Accounts create/reset/enable/disable/grant/revoke (`pages/Accounts.tsx`);
   - Budgets create/edit/delete (ticket 04);
   - Pricing create/delete (ticket 05);
   - Alerts ack/close + rules/channels CRUD (ticket 09).
   - Keep persistent inline `Alert`s for errors that need to stay visible
     (e.g. reveal-once secrets stay as-is).
3. **Auto-refresh** (`src/state/FiltersContext` or a small
   `RefreshContext.tsx` + `RefreshButton.tsx`)
   - Interval selector: Off (default) / 30 s / 1 min / 5 min, persisted under
     `localStorage` key `aiobs.refresh`.
   - A `refreshInterval` value exposed via a hook; dashboard queries
     (overview/metrics/costs/workflows/clients/agents, alerts/budgets on
     Manager) pass `refetchInterval` when enabled.
   - When enabled, the `RefreshButton` shows a subtle "auto" indicator; manual
     refresh remains immediate. Detail pages (ExecutionDetail) stay manual.
   - Stop polling when the tab is hidden (react-query default) and never poll
     on query errors more than the base cadence.

## Acceptance

- Every wired mutation shows a success toast on completion and an error toast
  with the server message on failure; toasts are dismissible and don't block
  the UI.
- Setting "1 min" on Manager causes the dashboard to refetch each minute
  (verifiable in the network tab); the setting survives a reload; "Off"
  restores the current behavior.
- No double-render or query-key churn (stable query keys); StrictMode-safe.
- Toasts are screen-reader announced (aria-live) and keyboard dismissible.

## Tests

- Ticket 15: Toast provider unit tests (stacking, auto-dismiss with fake
  timers, aria attributes); interval selector state test.
- Ticket 16: one page test asserting a toast appears after a mocked successful
  mutation.

## Comments
