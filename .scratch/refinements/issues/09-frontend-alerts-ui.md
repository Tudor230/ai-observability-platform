# 09 — Frontend: Alerts page (list, rules, channels)

Type: task
Status: resolved
Blocked by: 01, 07, 08
Area: audit item 7 (alerts)
Estimate: L

## Goal

A dedicated `/alerts` page where every role sees its scoped open alerts and can
acknowledge them when permitted, managers configure rules for their org units,
and admins/execs manage delivery channels.

## Changes

1. **Routing/nav**
   - `src/App.tsx`: lazy route `/alerts` (all authenticated roles).
   - `AppShell.tsx`: nav item "Alerts" (alert-triangle icon); move the open
     counter badge from the Manager link to Alerts; keep the topbar alert
     shortcut pointing here. Add `ROUTE_TITLES` entry.
2. **API layer** (`client.ts`, `hooks.ts`, `types.ts`)
   - `alerts.list({status?, severity?, q?, sort?, order?, limit?, offset?})`,
     `alerts.update(id, status)`.
   - `alertRules.list/create/update/delete` (+ `channel_ids`), `useAlertRules`.
   - `alertChannels.list/create/update/delete`, `useAlertChannels`
     (admin/exec only — gate fetch by role).
   - Types: `AlertRule`, `AlertRuleInput`, `AlertChannel`, `AlertChannelInput`.
3. **`src/pages/Alerts.tsx` — tabs**
   - **Open** (default): filter row (status, severity, debounced search),
     severity badges, message, dimension/scope label, `triggered_at`; per-row
     Ack / Close buttons when `item.can_ack`; optimistic refresh + toast
     (ticket 12) or inline feedback; pagination via `limit/offset` with
     "showing X of N".
   - **Rules** (manager/exec/admin only): sortable table (name, metric,
     thresholds, scope, channels count, enabled); "New rule" dialog (name,
     metric select, warning/critical numeric inputs with `critical >= warning`
     validation, scope picker via `SearchableSelect` — department/team/project
     options from the directory hooks, global option only for exec/admin,
     channel multi-select), edit, enable/disable toggle, delete (builtins show
     "system" and disable instead of delete, matching the 409).
   - **Channels** (admin/exec only): table (name, type, target, enabled) with
     create/edit dialog and delete confirm; hint that delivery is best-effort.
   - Client role: only the Open tab, no ack buttons.
   - Empty states: "no alerts" with a link to Rules (for managers) and a hint
     that alerts appear when thresholds/budgets are crossed.
4. **Client cost note**: keep alert display as-is for clients (threshold
   status, not raw cost detail), per spec open decision #1.

## Acceptance

- Managers land on Alerts, see scoped open alerts, ack/close them; a sibling's
  alert is not listed.
- Creating an `error_rate` rule for a team with channels selected shows up in
  the table and triggers alerts after evaluation; threshold validation blocks
  `critical < warning` before submit.
- Built-in rules cannot be deleted; disabling one stops its alerts.
- Admin/exec can create an email/Slack channel and link it to a rule; managers
  can select it but not edit channels.
- The nav badge counts match `/alerts` (status=open).

## Tests

- Covered by ticket 16 (Alerts page RTL: tabs by role, ack flow, rule dialog
  validation, channel CRUD visibility); manual verification with the live
  stack: create a rule via UI → `POST /alerts/evaluate` → alert appears.

## Comments

Implemented. New `/alerts` page (all roles) with three tabs: **Open** (debounced
message search, severity/status filters, scope labels, Ack/Close per
`can_ack`), **Rules** (manager/exec/admin: sortable-free table with metric
labels, warning/critical thresholds, scope, channel count, enable/disable,
edit dialog with metric/threshold/scope pickers and a channel multi-select,
builtin rows marked "system" with no delete), and **Channels**
(admin/exec: CRUD with email/Slack/webhook validation and the SMTP hint). New
`api.alerts.list/update`, `api.alertRules.*`, `api.alertChannels.*` (typed
inputs); hooks `useAlerts(params)`/`useAlertRules`/`useAlertChannels`. Nav item
with the open counter (moved from Manager) plus the topbar shortcut now point
to `/alerts`; Overview links updated; the alerts badge fetches for every
authenticated role (clients see their scoped alerts, no ack).

Evidence: `npm run lint` + `npm run build` clean (Alerts page code-split to
15.5 kB gzip 4.7), `npm test` 416 passed. Backend endpoints were live-verified
in tickets 06–08; role/tab RTL coverage lands in ticket 16.
