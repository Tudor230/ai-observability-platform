# Refinements v2 — email feedback round

Status: in progress (2026-10-12)
Source: colleague review + user clarifications
Convention: phase-ordered commits, one per ticket, on `feat/refinements`.

## Clauses from the review (settled)

1. **Remove the general filter band from every page** and replace it with a
   compact filter/sort UX (header popover + active chips; Engineering keeps
   inline search/status/sortable headers/pagination).
2. **Dropdown clipping** (`combobox__list` never flips; modals have no
   max-height): portal + flip + modal scroll.
3. **Block info banners removed** (the two named examples); no notification
   center/toast redesign requested.
4. **Alerts 2-state read**: acknowledge = read (stays visible); deletion is an
   explicit action, never automatic on read.
5. **Client role** is an outsider: no Requests tab/route; clients are
   provisioned by admins.
6. **Graphs**: go, full list (p99, status mix, cost by project, failures by
   kind, agent cost, budget burn-down).
7. **Enterprise gaps**: budgets — no audit trail; pricing — done; alerts — add
   channel *send test* + *delivery history* only.

## Tickets & phases

| # | Phase | Scope |
|---|---|---|
| 01 | 1 | Backend: block clients from `/requests`; scope `/departments`+`/teams` away from clients |
| 02 | 1 | Backend: alert status list filter (`open,acknowledged`) + `DELETE /alerts/{id}` (scoped) |
| 03 | 1 | Backend: `POST /alert-channels/{id}/test` + `alert_deliveries` table, recording, `GET /alert-deliveries` |
| 04 | 1 | Backend: `GET /failures/series` + `GET /budgets/{id}/series` (burn-down data) |
| 05 | 2 | Frontend: client nav/route removal + remove the two info banners |
| 06 | 2 | Frontend: combobox portal/flip + modal max-height/scroll |
| 07 | 2 | Frontend: filter redesign (header popover + chips), delete `FilterToolbar` |
| 08 | 2 | Frontend: alerts read/delete UX (default Active = open+acknowledged, Mark read, Delete) |
| 09 | 2 | Frontend: graphs pack (p99, ok/error stack, cost by project, failures by kind, agent cost, burn-down dialog) |
| 10 | 2 | Frontend: channel Test button + delivery-history card |

## Design notes

- **Filters**: `FiltersControl({dimensions})` button in `PageHeader` + popover
  with only the relevant fields; `FilterChips` under the header with removable
  chips + Clear all. URL-backed state stays (`FiltersContext`). Per page:
  Overview/Manager/Executive/Engineering (rich), Client (days+project),
  Projects/Project (days). Engineering keeps search/status inline.
- **Alerts**: list default `status=open,acknowledged` ("Active"); row shows the
  status badge; *Mark read* → acknowledged; *Delete* → confirm → hard delete
  (`DELETE`, scoped like ack). Dashboards/nav counters keep counting **open**
  only (unread).
- **Delivery history**: `alert_deliveries(id, alert_id?, channel_id?,
  channel_type, target, status, error?, created_at)`; recorded on every real
  send (per-channel and fallback webhook) and on test sends; UI lists the
  latest 20 in the Channels tab.
- **Graphs data**: failures-by-kind from a new scoped SQL series (group by day +
  `root_error_kind`); burn-down from per-day spend inside the budget window;
  the rest reuse `/metrics` + `/costs` data already returned.

## Verification

- Backend: pytest + ruff + mypy per ticket; migration upgrade/check/downgrade.
- Frontend: vitest + lint + build per ticket; coverage gate kept (80% lines).
- End of run: full backend suite, SDK suite, KPI gate, frontend coverage.
