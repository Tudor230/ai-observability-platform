# Refinements v1 — Search & Sort, Budgets, Pricing, Alerts, Graphs, UX, Coverage

Status: draft for review (planning session 2026-10-09)
Source: platform audit 2026-10-09, items **4, 5, 6, 7, 10, 11, 12**
Tickets: [`issues/01`](issues/01-backend-search-sort.md) – [`issues/17`](issues/17-sdk-coverage.md)

## 1. Why

The audit verified the roles/registration half of the platform is done (items
1–3, 9) but found seven gaps versus the product promise:

| # | Area | Audit verdict |
|---|------|---------------|
| 4 | Filtering / search / sort | Partial — filters work; no search on lists; no sort anywhere |
| 5 | Budgets | Partial — view only; admin-only CRUD; no department/team scope |
| 6 | Pricing | Partial — admin API exists; no admin UI |
| 7 | Alerts | Partial — env-driven engine only; no configurable rules, no email/msg channels, managers cannot create or acknowledge |
| 10 | More graphs | Partial — 9 chart instances; no latency/error/tool-call trends, no cost-by-model chart, no team dimension, Project has no charts |
| 11 | UX | Solid baseline; no toasts, no auto-refresh, no pagination, dead-end empty states, missing management UIs |
| 12 | Test coverage | Backend 86% (CI floor 80%); frontend app code 0%; SDK unmeasured |

This spec defines the target behavior, the data/API/UI changes, the test
strategy, and the ticket breakdown.

## 2. Current state (verified facts)

### 2.1 Search / sort (item 4)

- `GET /executions` supports `start|end|days|project_id|client_id|workflow|status|limit|offset`
  and SQL pagination, fixed order `started_at DESC, id DESC`
  (`backend/src/aiobs_backend/api/queries.py:70-101`). No `q`, no `sort`.
- `GET /alerts` supports `status|severity|limit|offset`, fixed
  `triggered_at DESC` (`backend/src/aiobs_backend/api/routes/alerts.py:15-57`). No `q`, no `sort`.
- `GET /pricing` returns all rows ordered by `provider, model`
  (`backend/src/aiobs_backend/api/routes/pricing.py:30-51`). No `q`, no `sort`.
- Frontend has no sort UI at all: `components/core/Table.tsx` has no sortable
  header support; no list page has a search input (only span-tree search via
  AgentPrism and `SearchableSelect` in forms).
- Filters live in `state/FiltersContext.tsx` (in-memory only, not in the URL);
  Manager drill-downs pass `?workflow=`/`?client_id=` which Engineering folds in
  once (`pages/Engineering.tsx:37-45`).

### 2.2 Budgets (item 5)

- Model: `Budget` has `project_id`, `client_id`, `workflow_name`, `amount`,
  `period` (anchor), `period_type` (day|week|month), `name`
  (`backend/src/aiobs_backend/models.py:377-393`).
- Windowed spend + 80%/100% alerts work (`backend/src/aiobs_backend/alerts.py:37-159`).
- **CRUD is admin-only** (`get_admin_key`): `GET/POST /budgets`,
  `DELETE /budgets/{id}` (`routes/budgets.py:50-110`). No update endpoint.
- Managers see `GET /budgets/status` scoped by **project only**
  (`budget_scope_clause`, `api/queries.py:36-43`); global budgets are excluded
  for scoped callers. No department/team budget scope exists.
- Frontend Manager page only renders utilization bars; the empty state says
  "Create a budget…" but there is no create action (`pages/Manager.tsx:262-291`).

### 2.3 Pricing (item 6)

- Backend: admin-guarded `GET/POST/DELETE /pricing` with `effective_from`,
  cache/reasoning rates, `model_match`; delete returns 409 when referenced by
  cost records (F30) (`routes/pricing.py`). Live-verified: 14 seeded rows.
- Frontend: **zero references** to pricing; no page, no hooks, no nav item.

### 2.4 Alerts (item 7)

- Engine: budget rules at `WARN_AT=0.8`/`CRITICAL_AT=1.0`; day-scoped rules for
  error rate, daily tokens, tool calls/execution, p95 latency, cost vs 7-day
  moving average. Thresholds come from `Settings` env vars
  (`config.py:44-50`), severity escalates at 2× (`alerts.py:162-163`).
- Delivery: best-effort POST of created alerts to `AIOBS_ALERT_WEBHOOK_URL`
  (`alerts.py:335-357`). No email, no Slack/Teams.
- No rule CRUD anywhere; rules are hardcoded/env-driven. Managers cannot create
  alerts; rule alerts are visible only to unrestricted callers
  (`alert_scope_clause`, `queries.py:22-33`); `PATCH /alerts/{id}` is admin-only
  (`routes/alerts.py:60-74`).
- Evaluation runs in the 60s background loop (`main.py:27-43`) and on demand via
  `POST /alerts/evaluate` (admin).

### 2.5 Graphs (item 10)

- Two chart components: `TrendChart` (line/bar/stack/dashed, 7 usages) and
  `BreakdownBars` (2 usages) — Overview ×3, Manager ×3, Executive ×2, Client ×1.
- `/metrics` already returns daily `error_rate`, `p50/p95/p99_duration_ms`,
  `tool_calls`, `total_cost`, tokens (`routes/metrics.py`); `/costs` supports
  dimensions `project|client|workflow|model|team` (`routes/costs.py:18`).
- Missing visuals: latency/percentile trend, error-rate trend, tool-call trend,
  cost-by-model chart (table only), team dimension chart (API exists, no UI),
  Project page charts (zero).

### 2.6 UX (item 11)

- Good: skeletons, `QueryError` banners on every view, empty states,
  dark/light, responsive breakpoints at 900/1100px, dialogs, reveal-once
  secrets, global 401 → login, CSRF header, manual `RefreshButton`.
- Missing: no toast/global feedback (all action feedback is inline), no
  auto-refresh (`main.tsx:23-25` — `staleTime: 15s`, `refetchOnWindowFocus: false`),
  no pagination on Engineering beyond "Load more" (`pages/Engineering.tsx:162-166`),
  empty states that point at actions that do not exist (budgets), no management
  UI for pricing/budgets/alert rules, minor a11y gaps (no table `caption`,
  no `aria-sort`, charts lack accessible labels).

### 2.7 Coverage (item 12)

- Backend: **113 tests, 86%** measured; CI gate `--cov-fail-under=80`
  (`backend.yml:57-58`).
- Frontend: 414 tests pass but app code (pages/components/state) is **0%**;
  tests are almost all vendored AgentPrism data logic + 3 `lib/` files.
  Vitest config has no jsdom, no RTL, no coverage provider, includes only
  `src/**/*.test.ts` (`frontend/vite.config.ts:39-42`). CI runs `npm test` with
  no coverage gate.
- SDK: 161 passed / 1 skipped; no coverage measurement or floor.

## 3. Design by area

### 3.1 Search & sort (item 4)

**Backend — new query params**

| Endpoint | New params | Semantics |
|---|---|---|
| `GET /executions` | `q`, `sort`, `order` | `q`: case-insensitive substring over `trace_id`, `workflow_name`, `error_message`. `sort` ∈ `started_at` (default) \| `duration_ms` \| `total_cost` \| `total_tokens` \| `error_count` \| `status`. `order` ∈ `desc` (default) \| `asc`. SQL-side, whitelist-mapped, stable `id` tiebreaker. |
| `GET /alerts` | `q`, `sort`, `order` | `q` over `message`; `sort` ∈ `triggered_at` (default) \| `severity`; same `order`. |
| `GET /pricing` | `q`, `sort`, `order` | `q` over `provider`/`model`; `sort` ∈ `provider` (default) \| `model` \| `effective_from`; feeds the pricing UI. |

- Unknown enum values → **422** (consistent with F32).
- Scoping semantics unchanged: search/sort compose with the existing
  `require_access`/scope filters; `total` reflects the filtered count.

**Frontend**

- New `SortableTh` support in `components/core/Table.tsx` (`sortKey`, `active`,
  `direction`, `onSort`, `aria-sort`) — small, dependency-free.
- `pages/Engineering.tsx`: debounced search box (300 ms), sortable columns
  (Started, Duration, Tokens, Cost, Status), URL-synced `q|sort|order|status`
  via `useSearchParams` so links are shareable.
- `FiltersContext` moves to URL query params (replace-navigation, no history
  spam): `days|project_id|client_id|workflow` become URL-backed, with the
  existing Manager drill-down links (`?workflow=`, `?client_id=`) handled
  natively by the same mechanism. API contract unchanged.
- Manager aggregate tables get client-side sorting in the same ticket
  (datasets are small; no API change needed there).

### 3.2 Budgets (item 5)

**Model** (`backend/src/aiobs_backend/models.py`):

- Add nullable `department_id` FK→`departments.id` and `team_id` FK→`teams.id`
  to `Budget`, indexed. `project_id`/`client_id`/`workflow_name` stay as
  optional AND-filters. One Alembic revision.

**Authorization (manager-managed budgets)**

- `GET /budgets`, `GET /budgets/status`, `POST /budgets`, `PATCH /budgets/{id}`,
  `DELETE /budgets/{id}`:
  - admin key / admin session → unrestricted.
  - `exec` (global) → unrestricted.
  - `manager` → only budgets whose scope they cover (`covers_scope` semantics:
    department manager covers its teams/projects; team manager covers its
    projects).
- **Scoped-create rule**: a manager-created budget must carry at least one of
  `department`, `team`, `project` (client/workflow are additional filters on
  top). Exec/admin may create global (unscoped) budgets. This keeps manager
  budgets attributable to their org units and fixes the current leak where
  client/workflow budgets would aggregate across all projects.
- New `PATCH /budgets/{id}`: update `name|amount|period|period_type` (+ scope
  fields), same authorization; period changes re-anchor the window.
- `budget_spend` extended: join `Project→Team` when `department_id`/`team_id`
  are set and filter accordingly. Global (unscoped) budgets stay exec/admin
  only.
- `budget_scope_clause` extended to visibility = project in allowed set OR team
  in allowed teams OR department in allowed departments (exec/admin: all).
  A new `allowed_scope_ids()` helper returns the department/team/global sets
  alongside the existing `allowed_project_ids`.
- API responses gain `department`/`team` (external names) and a `scope` label
  for display.

**Frontend**

- Manager page gains a **Budgets management** section: list with utilization +
  scope label, "New budget" dialog (name, amount, period_type, anchor date,
  scope: department/team/project via `SearchableSelect`, optional client /
  workflow filters), edit (PATCH) and delete (confirm dialog with the
  `Budget exceeded`/referenced semantics). Exec sees all; manager sees covered
  ones. Empty state links to the dialog instead of the current dead end.

### 3.3 Pricing UI (item 6)

- New admin-only route `/pricing` ("Pricing" nav item under Accounts in the
  admin group of `AppShell.NAV_ITEMS`; `RequireRoles allow={["admin"]}`),
  lazy-loaded like the others.
- Page: search box (API `q`), sortable table (provider, model, match,
  input/output/cache/reasoning prices, currency, `effective_from`), "Add price"
  dialog (all `PricingIn` fields, `effective_from` default = now), delete with
  confirm and 409 handling ("referenced by cost records — add a newer
  effective-dated price instead").
- **No edit** in v1: cost history is immutable once used (F30); corrections are
  new effective-dated rows. Deletion of unreferenced rows stays available.
- `api/client.ts`: `pricing.list(q?)`, `pricing.create(body)`, `pricing.delete(id)`
  + a `usePricing` hook; types in `api/types.ts`.

### 3.4 Alerts (item 7)

**Alert rules model** — new table `alert_rules`:

| Column | Notes |
|---|---|
| `id` String(32) PK | |
| `name` String(120) | |
| `metric` String(40) | `error_rate\|daily_tokens\|tool_calls_per_execution\|p95_latency\|cost_anomaly` |
| `warning_threshold` Numeric | critical ≥ warning enforced |
| `critical_threshold` Numeric | |
| `scope_type` String(20) | `global\|department\|team\|project` (polymorphic like memberships) |
| `scope_id` String(32) nullable | required except global |
| `enabled` Boolean default true | |
| `builtin` Boolean default false | seeded system rules; deletable only when disabled/edited by admin |
| `created_by` String(32) nullable | |
| `created_at` | |

- **Seeding**: on startup, if `alert_rules` is empty, seed the 5 current
  built-in rules from `Settings` (global scope, `builtin=True`) so the KPI gate
  and existing behavior are preserved; evaluation then reads only DB rules.
- **Evaluation** (`evaluate_threshold_rules` refactor): for each enabled rule,
  resolve its project set (global → all; scope → allowed set via
  `allowed_project_ids`-style resolution) and compute the metric over the
  current UTC day **restricted to those projects** (and the caller-independent
  full set). `error_rate`/`p95` are ratios/percentiles over that slice; token
  and cost sums likewise. Warning/critical alerts are emitted separately with
  dedupe per `(rule, day, severity)`.
- **CRUD**: `GET/POST /alert-rules`, `PATCH/DELETE /alert-rules/{id}`.
  - admin/exec: any rule (global included).
  - manager: create/edit/delete rules only within their covered scope
    (`covers_scope` semantics); global rules are admin/exec-only.
  - deleting a `builtin` rule is rejected (409) — disable (`enabled=false`) or
    edit thresholds instead.
  - Validation: 422 on unknown metric, inverted thresholds
    (`critical < warning`), scope the role cannot hold.
- **Alert record**: add `rule_ref` String(32) nullable to `Alert` (Alembic);
  threshold alerts set `rule_ref = rule.id`, budget alerts keep
  `dimension="budget"`. This is the anchor for scoped acknowledgments.

**Channels** — new table `alert_channels`:

| Column | Notes |
|---|---|
| `id`, `type` (`email\|slack\|webhook`), `name`, `target` (email address or URL), `enabled`, `created_by`, `created_at` |

- Join table `alert_rule_channels` (`rule_id`, `channel_id`, unique pair).
- Routing: a rule with channels → send to exactly those; a rule without
  channels → fall back to `AIOBS_ALERT_WEBHOOK_URL` (back-compat).
- Senders (`alerts/delivery.py`): `email` via stdlib `smtplib` using new
  settings `AIOBS_SMTP_HOST|PORT|USERNAME|PASSWORD|FROM|STARTTLS`; `slack` posts
  `{"text": …}`; `webhook` posts the alert JSON as today. Best-effort:
  failures are logged, never break evaluation; no delivery journal in v1 (fog).
- Channel CRUD: `GET/POST /alert-channels`, `PATCH/DELETE /alert-channels/{id}`
  — **admin/exec only** (channel targets are org resources); managers select
  from enabled channels when editing their rules.

**Scoped acknowledgment**

- `PATCH /alerts/{id}` gains session authorization: admin key OR exec OR a
  manager covering the alert's scope — budget alert → the budget's
  department/team/project; rule alert → the rule's scope; global rule/budget →
  exec/admin only. Status transitions stay `open→acknowledged→closed` (and
  reopen for admin). Same validation, no message/status injection.
- `GET /alerts` result gains `can_ack` per item (server-computed) and keeps the
  existing scope filtering; **rule alerts become visible to scoped callers when
  the rule's scope intersects their allowed set** (extend `alert_scope_clause`
  with the rule_ref join).

**Frontend**

- New `/alerts` route + nav item (all roles; counter badge moves from
  `/manager` link to `/alerts`), three tabs:
  - **Open** (default): filterable list (status, severity, search), severity
    badges, dimension/scope, timestamps; Ack/Close buttons when `can_ack`.
  - **Rules** (manager/exec/admin): table + create/edit dialog (name, metric,
    warning/critical thresholds, scope picker, channel multi-select);
    built-in rows marked "system", delete disabled, disable toggle available.
  - **Channels** (admin/exec): table + create/edit dialog (type, target,
    enabled), test note "delivery is best-effort".
- Client role sees only its scoped alerts (no rules/channels tabs, no ack).

### 3.5 Graphs (item 10)

All frontend, on existing API data:

1. **Latency trend** (Overview + Manager): `TrendChart` lines for
   `p50_duration_ms` and `p95_duration_ms` from `useMetrics("total")`
   (already returned); `formatMs` formatter; empty state.
2. **Error-rate trend** (Overview): line chart of `error_rate` (percent
   formatter) alongside the existing executions chart.
3. **Tool-call trend** (Manager): line/bar of `tool_calls` per day.
4. **Cost by model chart** (Executive): `BreakdownBars` from
   `useCosts("model")` (replaces/complements the current table) with
   provider·model labels.
5. **Team cost chart** (Manager, exec/admin only — scoped callers get 403):
   `BreakdownBars` from `useCosts("team")`.
6. **Project page charts**: executions trend + cost trend using
   `useMetrics("project", filters, projectId)` (scoped-correct) plus per-project
   overview KPIs that already render.

Chart reuse only; no new chart libraries. Each chart gets loading, error and
empty states per the existing page patterns.

### 3.6 UX (item 11)

1. **Toasts**: `ToastProvider` + `useToast()` in `src/components/core`
   (auto-dismiss ~4 s, variant success/danger/info, `role="status"`,
   stacked, imperative API `toast.success("...")`). Wire into every mutation
   handler that currently sets a local error/feedback string: project keys,
   requests submit/approve/reject/cancel, accounts create/reset/grant/revoke,
   budgets, pricing, alerts/rules/channels. Inline `Alert`s stay for persistent
   errors; toasts provide success/failure feedback.
2. **Auto-refresh**: interval selector on dashboard pages (Off / 30 s / 1 min /
   5 min, persisted in `localStorage`) wired to react-query `refetchInterval`
   per dashboard query; default **Off** to preserve current behavior. The
   manual `RefreshButton` stays.
3. **Pagination**: Engineering replaces "Load more" with prev/next + page-size
   (25/50/100) and "showing X–Y of N" from the existing `limit/offset/total`
   API; page state in the URL (couples with ticket 02's URL filters).
4. **Empty-state CTAs**: every empty state that references an action links to
   it (Requests registration, Budgets dialog, Pricing page, Alerts rules).
5. **A11y pass**: table `caption` (visually hidden) + `scope="col"` headers,
   `aria-sort` on sortable headers, `role="img"` + `aria-label` on charts,
   dialog focus trap/ESC (verify `core/Dialog`), toast `aria-live`, focus-visible
   states. Lint rule not required.

### 3.7 Test & coverage strategy (item 12)

**Frontend infrastructure** (ticket 14):

- Dev deps: `@testing-library/react@^16`, `@testing-library/user-event`,
  `@testing-library/jest-dom`, `jsdom`, `@vitest/coverage-v8@3.2.7`.
- `vite.config.ts` test block: `environment: "jsdom"` for `**/*.test.tsx`
  (RTL) via `environmentMatchGlobs` (keep node for data tests),
  `include: ["src/**/*.test.{ts,tsx}"]`, `setupFiles` with jest-dom,
  coverage provider `v8` with `reporter: ["text", "lcov"]`, excludes:
  `src/components/agent-prism/**` (vendored), `src/main.tsx`,
  `src/vite-env.d.ts`.
- `package.json`: `"test:coverage": "vitest run --coverage"`; CI frontend
  workflow runs it with a `--coverage.thresholds.lines` floor (ratchet).

**Coverage targets** (non-vendor `src/**`):

| Scope | Target | Notes |
|---|---|---|
| Backend | 80% | already met (86%, CI floor) — no change |
| Frontend app code | **≥80% lines/statements/functions** | phased: gate at measured baseline in ticket 14, ratcheted to 80 in ticket 16; `src/lib` already ~84% |
| SDK | **≥80%** | measure first with `pytest-cov`; raise tests if below, otherwise ratchet from baseline (ticket 17) |

**Frontend test plan** (tickets 15–16):

- `state/` (AuthContext role/cost visibility, FiltersContext URL sync,
  ThemeContext), `api/client.ts` (qs, CSRF header, 401 handler, error surfacing),
  `api/hooks.ts` (query keys invalidated).
- `components/core` (Table sorting, Dialog open/close/ESC, Feedback,
  SearchableSelect filtering/keyboard, Metric/Delta tones), `components/charts`
  (render/empty state).
- Page-level RTL tests with a `QueryClientProvider` + `MemoryRouter` harness and
  mocked `api` module: Login, Engineering (filters/search/sort/pagination),
  Requests (submit + approve/reject flow), Accounts (create, grant/revoke),
  Project (keys add/rotate/revoke), Manager (budgets/alerts), Executive
  (charts + forecast), Client (cost fields absent), Alerts (tabs + ack).
- Prefer user-visible assertions (`getByRole`, `findByText`) over snapshots.

**SDK**: `pytest-cov` in the dev group; CI `--cov=ai_observability
--cov=mock_workflows --cov-fail-under=<floor>` (floor set to the measured value
in ticket 17 if ≥80%, otherwise tests are added first).

## 4. Data model & migrations (one revision each)

| # | Migration | Change |
|---|---|---|
| 1 | `budgets` scope | add `department_id`, `team_id` (nullable FKs, indexed) |
| 2 | `alert_rules` | new table (+ indexes on `enabled`, `scope_type/scope_id`) |
| 3 | `alerts.rule_ref` | add nullable `rule_ref` String(32), index |
| 4 | `alert_channels` + join | new tables (`unique(rule_id, channel_id)`) |

## 5. API surface changes (summary)

| Method & path | Change | Auth |
|---|---|---|
| `GET /executions` | `q`, `sort`, `order` | unchanged |
| `GET /alerts` | `q`, `sort`, `order`; items gain `can_ack`, rule-scope visibility | unchanged |
| `PATCH /alerts/{id}` | session + scoped-manager ack | admin key / exec / covering manager |
| `GET /pricing` | `q`, `sort`, `order` | admin |
| `GET/POST /budgets`, `GET /budgets/status` | dept/team scope, scoped visibility, scope labels | admin/exec + covering manager |
| `PATCH /budgets/{id}` | new | admin/exec + covering manager |
| `DELETE /budgets/{id}` | scoped auth | admin/exec + covering manager |
| `GET/POST /alert-rules`, `PATCH/DELETE /alert-rules/{id}` | new | admin/exec any; manager covered scopes |
| `GET/POST /alert-channels`, `PATCH/DELETE /alert-channels/{id}` | new | admin/exec |

## 6. Config/env additions

| Var | Purpose |
|---|---|
| `AIOBS_SMTP_HOST|PORT|USERNAME|PASSWORD|FROM|STARTTLS` | email channel |
| (existing) `AIOBS_ALERT_WEBHOOK_URL` | fallback channel for rules without explicit channels |
| (existing) `AIOBS_ALERT_*` thresholds | used to seed built-in rules when the table is empty |

## 7. Sequencing & ticket index

| # | Ticket | Area | Est | Blocked by |
|---|---|---|---|---|
| 01 | [Backend: search + sort](issues/01-backend-search-sort.md) | 4 | M | — |
| 02 | [Frontend: Engineering search/sort + URL filters](issues/02-frontend-search-sort-url.md) | 4 | M | 01 |
| 03 | [Backend: budget scopes + scoped CRUD](issues/03-backend-budget-scopes.md) | 5 | M | — |
| 04 | [Frontend: budgets management UI](issues/04-frontend-budgets-ui.md) | 5 | M | 03 |
| 05 | [Frontend: pricing admin UI](issues/05-frontend-pricing-ui.md) | 6 | S | 01 |
| 06 | [Backend: alert rules + evaluation](issues/06-backend-alert-rules.md) | 7 | L | — |
| 07 | [Backend: alert channels + delivery](issues/07-backend-alert-channels.md) | 7 | M | 06 |
| 08 | [Backend: scoped alert acknowledgment](issues/08-backend-scoped-ack.md) | 7 | S | 06 |
| 09 | [Frontend: Alerts page (list/rules/channels)](issues/09-frontend-alerts-ui.md) | 7 | L | 01, 07, 08 |
| 10 | [Frontend: latency/error/tool-call trends](issues/10-frontend-trend-graphs.md) | 10 | S | — |
| 11 | [Frontend: model/team/project graphs](issues/11-frontend-coverage-graphs.md) | 10 | M | — |
| 12 | [Frontend: toasts + auto-refresh](issues/12-frontend-toasts-refresh.md) | 11 | M | — |
| 13 | [Frontend: pagination, empty-state CTAs, a11y](issues/13-frontend-pagination-a11y.md) | 11 | M | 02 (aria-sort) |
| 14 | [Frontend: test infra + coverage gate](issues/14-frontend-test-infra.md) | 12 | M | — |
| 15 | [Frontend: unit tests (state/core/api)](issues/15-frontend-unit-tests.md) | 12 | L | 14 |
| 16 | [Frontend: page tests + 80% gate](issues/16-frontend-page-tests.md) | 12 | L | 14 |
| 17 | [SDK: coverage measurement + floor](issues/17-sdk-coverage.md) | 12 | S | — |

Parallel tracks: **backend** (01, 03, 06→07/08) → **frontend features**
(02→13, 04, 05, 09, 10, 11, 12) → **tests** (14→15/16, 17).

## 8. Decisions (settled 2026-10-09)

1. **Client alert visibility**: clients keep seeing their projects' budget
   alerts — they are threshold status, and messages must never include per-call
   cost detail.
2. **Channel management**: channels stay admin/exec-managed; managers select
   from enabled channels when editing their rules (no manager-created channels).
3. **Frontend coverage ratchet**: gate at the measured baseline in ticket 14
   first, then ratchet to 80% in ticket 16.

## 9. Out of scope / fog

- Alert delivery journal/retries per channel; dead-letter queue.
- Per-user alert subscriptions/notification preferences.
- Budget forecast-based alerts (projected overspend).
- Column pinning/export (CSV) on tables.
- Server-side sort for the small aggregate lists (workflows/clients/agents) —
  handled client-side.
- Playwright/E2E browser suite (remains a documented deferral; RTL covers
  integration level).
- Membership lifecycle/manager reassignment and approval notifications (roles
  effort fog, unchanged).
