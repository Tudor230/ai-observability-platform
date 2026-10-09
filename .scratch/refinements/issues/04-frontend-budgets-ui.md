# 04 — Frontend: budgets management UI

Type: task
Status: resolved
Blocked by: 03
Area: audit item 5 (budgets)
Estimate: M

## Goal

Give managers (and exec/admin) a working budgets section: list with utilization
and scope, create/edit dialog, delete with confirmation. Replace the current
read-only bars and dead-end empty state.

## Changes

1. **`src/api/client.ts` + `src/api/hooks.ts`**
   - `budgets.list()`, `budgets.create(body)`, `budgets.update(id, body)`,
     `budgets.delete(id)`; `useBudgets()` query + mutation hooks that invalidate
     `["budgets"]` on success.
   - Types: `Budget`, `BudgetInput` in `src/api/types.ts` (amount, period,
     period_type, name, department/team/project/client/workflow).
2. **`src/pages/Manager.tsx` — Budgets panel**
   - Replace the read-only list with a management card:
     - Rows: name, scope label, amount, current spend, utilization (existing
       `Progress`, unclamped number), period window dates; Edit + Delete
       actions.
     - "New budget" button in the card header opens the dialog.
     - Empty state: description + primary button opening the same dialog.
   - New `BudgetDialog` component (in the page file or
     `components/domains/BudgetDialog.tsx`): name, amount, `period_type`
     (day/week/month), anchor date (default today), scope pickers
     (`SearchableSelect` for department → team → project, with the selected
     scope determining which follow-up filters are offered), optional client /
     workflow text inputs. Validation mirrors the backend (manager: scope
     required — the dialog hides create for unscoped managers/exec? exec gets a
     "Global" option).
   - Delete: confirm `Dialog` explaining that history/future alerts for the
     budget stop; surface 403/404 errors via toast (ticket 12) or inline alert
     until then.
3. **Role behavior**
   - Manager: create/edit/delete within their directory options only.
   - Exec/admin: additionally "Global" scope (no department/team/project).
   - Scoped clients never reach this page (route already manager/exec).

## Acceptance

- Manager creates a department budget from the dialog; it appears with
  utilization and the correct period window; the empty state is gone.
- Edit updates amount/period and the utilization recalculates.
- Delete removes it after confirmation; failures (403/409) show a readable
  message and the row stays.
- Exec can create a global budget; a manager cannot (no "Global" option).
- Manager's directory pickers only show their covered departments/teams/projects.

## Tests

- Covered by ticket 16 page tests (Manager budgets: create → list → edit →
  delete with mocked API); manual verification against the live stack.

## Comments

Implemented. Manager's Budgets panel is now a management card: scope label per
row, Edit/Delete actions, "New budget" in the header, and an empty state with a
create CTA (`EmptyState` gained an `extra` slot for it). New
`components/BudgetDialog.tsx` covers create + edit (name, amount, period type +
anchor date, department→team→project SearchableSelects that filter each other,
optional client/workflow filters, and a "Global budget" checkbox shown only to
exec/admin). `api.budgets.list/create/update/remove` + `patch` helper, typed
`BudgetInput`/extended `BudgetStatus`, `useBudgets`, and `useTeams(department?)`
were added; mutations invalidate `["budgets"]`.

Evidence: `npm run lint` + `npm run build` clean, `npm test` 416 passed;
backend endpoints live-verified earlier in ticket 03. RTL coverage for the
create/edit/delete flow lands in ticket 16.
