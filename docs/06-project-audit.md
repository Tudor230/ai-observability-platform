# Project Audit — AI Observability Platform

Date: 2026-09-15 · Commit audited: `2cb02b6` (branch `feat/backend-frontend-plans`)
Scope: `docs/01–05`, `plans/`, `sdk/`, `shared/aiobs_contracts/`, `backend/`, `frontend/`,
`.github/workflows/`, `docker-compose.yml`.

Method: four independent deep reviews (backend, frontend, SDK/contracts/CI, requirements
coverage) + live verification against the running Docker stack (Postgres `:5432`,
Phoenix `:6006`, backend `:8000`, dashboard `:8080`) and the project's own test/KPI scripts
executed in a throwaway container (no host changes).

---

## 1. Verdict (answers to the review questions)

**Is the project complete?** No. It is a **working vertical slice** (SDK → OTLP → normalize →
classify → cost → API → 3 dashboard views) that passes its own KPI gate 14/14 — but it
implements the *technical observability* half of the assignment and roughly half of the
*FinOps/platform* half.

**Are steps left?** Yes — see §4 "Remaining work vs the plans". Highest-impact missing:
read-side auth/tenancy, alert taxonomy beyond budgets, team/service attribution, budget
periods, persistent Postgres, honest KPI measurement, agent-efficiency UI, retention/ops.

**Are we missing something important?** Yes: (a) the alert engine covers 1 of 7 promised
categories; (b) reads are unauthenticated and project scope is cosmetic; (c) the KPI gate
does not measure the KPIs as docs/05 defines them; (d) unpriced models silently become `$0`
in every aggregate; (e) no DB persistence/backup; (f) the Manager/Executive cost panels are
currently broken by an API field mismatch.

**Is the implementation right?** The core pipeline is sound and impressive (contract-driven,
idempotent-intent, deterministic mocks). But there are real correctness defects: partial
OTLP batches can corrupt/delete executions (F02), pricing history (`effective_from`) is
ignored (F08), budgets never roll over (F09), money is accumulated as floats (F12), and the
`/costs` ↔ UI contract is broken (F01). Tests are thin (17 backend tests) and do not cover
any of the P0s.

**Could things be done better?** Yes — main themes: aggregate in SQL instead of Python
(F11/F26); use `Decimal`/`NUMERIC` end-to-end (F12); move SDK retry/root logic into a
`SpanProcessor` instead of buffering whole traces (F14); generate the frontend API types from
OpenAPI and add a contract test (root cause of F01); make the KPI gate assert the docs/05
formulas (F05).

**Is the frontend as it should be and does it display the right data?** The shell, routing,
code-splitting and formatting are fine, but: the two headline FinOps visuals (Cost by
workflow/client, Cost per client/model) read `total_cost` from an endpoint that returns
`cost` → **they render `$0`/"—" even with data** (F01, reproduced live); the global filter bar
is not applied to metrics/trends/forecast/alerts (F15); errors are indistinguishable from
empty data (F23); several promised panels/actions are missing (F24). **Yes, it can be
verified** — procedure in §3, and we did the API/DB half; the UI half needs either the fix +
a contract test or Playwright.

**Does the frontend display the correct data for the respective users?** No. The role
switcher is three `NavLink`s (AppShell.tsx:48-68) — navigation, not access control — and the
backend reads are anonymous, so *everyone* sees the finance view. Persona-specific scoping
does not exist in v1 (recorded as a known decision, but it means the docs/04 §4.9 role
requirement is unmet).

**Is the app the right fit for the given task?** For the demo narrative ("what happened, what
did it cost, why did it fail") it is a credible, coherent fit and clearly built with care.
For the *stated* platform promise (multiple teams, shared FinOps, alerting, governance) it is
a single-tenant prototype: polish (shared contracts, retry inference) sits next to missing
basics (auth, tenancy, alert taxonomy, persistence, KPI honesty).

---

## 2. Live verification performed (facts, not opinions)

- Backend suite (in container, against `aiobs_test` on the shared Postgres): **17 passed** —
  i.e. only 17 backend tests exist (`tests/test_classify.py`, `test_ingest.py`,
  `test_pricing.py`).
- `kpi_gate.py` against the running backend: **14/14 scenarios PASS; "KPIs PASSED"** (KPI 1
  coverage, KPI 2 cost, classification). The wire path works end-to-end.
- DB after the gate: 15 executions, 55 spans, 1 cost record, `sum(total_cost)=0.000450`,
  `sum(total_tokens)=1577`, all for `proj-1`.
- **14 of 15 executions have `total_cost = NULL`** (only the KPI's synthetic trace is priced).
  `/api/v1/costs?dimension=client` returns `client-42: cost 0.0` — unpriced cost is silently
  folded to `$0` in the API (confirms F12's aggregation concern with live data).
- `/api/v1/costs` response items contain **`cost`** (routes/costs.py:59,66,94) while
  `Manager.tsx:30-31` and `Executive.tsx:73,92` read **`total_cost`** → reproduced mismatch
  (F01). `/api/v1/workflows` and `/api/v1/clients` do return `total_cost`, so the Manager
  tables work while the Manager charts stay at `$0` — an inconsistency that is easy to demo,
  and easy to miss in review.
- `/api/v1/agents` returns one agent at `0.0`; the per-span loop that double counts
  (`routes/agents.py:40-49`) is confirmed in code.
- Role switcher is `NavLink`s only (`AppShell.tsx:54-68`); filters exist in
  `FiltersContext` but are not threaded into all queries.
- Postgres data survives container restarts only if you don't `down` it: the compose service
  has **no volume** and no `restart:` policy (`docker-compose.yml:8-22`).
- Backend API keys: admin header is `x-admin-key`; reads need nothing; CORS responds
  `access-control-allow-origin: *`.

---

## 3. How to verify the frontend data path (and what to automate)

Today (manual, ~2 min):

1. Seed: the stack now has data from the KPI gate; otherwise
   `docker exec ... psql -U postgres -d aiobs -c "\dt"` and run `uv run aiobs-mock
   --endpoint http://localhost:8000 --api-key <key> --project-id proj-1` from `sdk/`.
2. Compare, for the same filters:
   - DB: `SELECT sum(total_cost), sum(total_tokens) FROM executions;`
   - API: `/api/v1/overview`, `/api/v1/costs?dimension=client`, `/api/v1/workflows`.
   - UI: open Manager/Executive and the browser devtools Network tab.
3. Expected today: API/DB agree; **UI charts show `$0`/"—"** because of F01 → that is the
   regression to fix.

To automate (recommended):

- A backend **contract test** asserting response keys against `openapi.json`
  (would have caught F01).
- **OpenAPI-generated types** for `frontend/src/api/types.ts` (kills the whole class).
- A **Playwright smoke** per view on a seeded compose stack (docs/05 §5.4 "dashboard
  validation" is otherwise unverified — there is no browser test today).

---

## 4. Remaining work vs the plans

Backend (`plans/backend.md`): `GET /workflows/{id}`; `PUT /pricing` and `PUT /budgets`;
project disable/revoke endpoints; nested failure tree in `/executions/{id}`;
`execution_metrics` entity; `workflows.latest_version`; `user.id` parsed/used; retrieval and
agent-call metrics in rollups; agent/team rollups; alert rules catalog; retry re-derivation;
`failed_agents`/`failed_tools`; Alembic actually applied (image doesn't even copy
`alembic/`); K8s per docs/04 §4.7 (or an ADR descoping it).

Frontend (`plans/frontend.md`): agent-efficiency panel (`useAgents` is dead code);
failure **tree**; drill-down links chart→executions; pagination + total; status filter UI;
alert ack/close UI; unpriced badge; live/polling refresh; role differentiation.

SDK (`plans/sdk.md`): background-worker mode; cache/reasoning token validation/backfill;
LlamaIndex retry/timeout/tool-failure scenarios; kind-override hook made public/documented.

---

## 5. Findings

Severity: **P0** = breaks the demo or the promise; **P1** = major gap/correctness; **P2** =
should fix before "done"; **P3** = polish. Each finding has evidence and a concrete fix.

### P0 — blockers

---

**F01 [P0] Manager/Executive cost visuals are broken by an API field mismatch**
Evidence: backend emits `cost` (`backend/src/aiobs_backend/api/routes/costs.py:59,66,94`);
frontend reads `total_cost` (`frontend/src/pages/Manager.tsx:30-31`,
`frontend/src/pages/Executive.tsx:73,92`; wrong type at
`frontend/src/api/types.ts:101`). Reproduced live: `/costs?dimension=client` returns
`{"key":"client-42","cost":0.0,...}` while the UI looks for `total_cost`.
Why it matters: the two headline FinOps visuals (manager "Cost by workflow/client",
executive "Cost per client/model") render `$0`/"—" with real data; the Manager tables
(workflows/clients endpoints) do show `total_cost`, so the UI contradicts itself.
Fix: return `total_cost` (or accept both) in `/costs`; update `types.ts`; add a contract
test that asserts `/costs` item keys against `openapi.json`; generate the types from
OpenAPI to prevent recurrence. Verify by re-running §3.

---

**F02 [P0] Partial OTLP batches corrupt or delete executions (idempotency claim is false)**
Evidence: `backend/src/aiobs_backend/ingest/pipeline.py:87-102` treats any span whose parent
is not in the *current batch* as a root; `process_trace` deletes the existing execution,
spans and cost rows **before** validating the new root (`pipeline.py:126-141`). A
children-only batch (normal with batching/retries) either creates a bogus execution named
after a child span (business identity lost) or — if it arrives after the full trace —
replaces the correct execution with the partial one. Deletion also happens when
`root is None` (lines 130-136 execute before the check at 139-141).
Why it matters: silently wrong traces/executions and destroyed history; the ADR and map
tickets advertise per-trace idempotent recompute.
Fix: validate the root (and project identity) **before** touching existing rows; merge
spans per `(trace_id, span_id)` with upsert, delete only spans absent from the batch; if a
batch has no valid root, buffer it (or ingest spans as "pending") instead of deleting.
Add regression tests: children-first batch, split batch, re-sent partial batch.

---

**F03 [P0] `kpi_gate.py` destroys the default database it targets**
Evidence: `backend/scripts/kpi_gate.py:29-32` defaults to `.../aiobs` and `:68-69` calls
`db.drop_all()` / `db.create_all()`. The README instructs running it as-is.
Why it matters: the project's own "validation" script wipes the demo/dev DB by default;
one accidental run during the demo destroys the data.
Fix: require `AIOBS_KPI_DATABASE_URL` to end in `_test`/`_kpi` (or require
`AIOBS_KPI_ALLOW_RESET=1`); refuse otherwise with a clear error; default to `aiobs_test`.

---

**F04 [P0] Alert engine implements 1 of 7 promised categories**
Evidence: `backend/src/aiobs_backend/alerts.py` evaluates only budgets (warn ≥80%,
critical ≥100%). docs/03 §3.12 and `plans/backend.md §10` promise cost, token, latency,
error-rate, excessive-tool-call, budget and moving-average anomaly rules; docs/05 §5.4
requires a scripted abnormal-consumption alert scenario; no such scenario exists.
Why it matters: "detect abnormal consumption and inefficient executions" (docs/01 §1.2.7)
is a core objective and is unimplemented; the alert badge in the UI counts only budgets.
Fix: add threshold rules over `daily_metrics` (tokens/day, p95 latency, error rate, tool
calls/execution) plus a simple moving-average deviation rule, evaluated by the existing
scheduler; extend `kpi_gate.py` with the docs/05 §5.4 scenario and assert the alert row.

---

**F05 [P0] The KPI gate does not measure the KPIs as docs/05 defines them**
Evidence: KPI 1 (docs/05 §5.2 = captured/expected events %) is asserted as
`total >= 14` / `max_tokens >= 14` (`kpi_gate.py:135-139`); KPI 2's Cost Error % formula is
never computed — it checks one hard-coded trace built by the backend's own helper
(`kpi_gate.py:93-119`), not an SDK-emitted trace; attribution (§5.3) and the §5.4 alert
scenario are not asserted; classification checks only 3 of 6 failure kinds
(`kpi_gate.py:149`).
Why it matters: the repo reports "KPIs PASSED" — a reviewer comparing against docs/05 will
find the measurement does not implement the definition. This is a credibility risk on the
assignment's own success criteria.
Fix: per mock scenario, declare expected spans/attributes/tokens; compute coverage % and
`|expected−actual|/expected` cost error on an SDK-produced priced trace; assert
`client_id`/workflow attribution; assert all failure kinds; add the alert scenario.

### P1 — major

---

**F06 [P1] Read APIs are unauthenticated; CORS is `*`; default secrets everywhere**
Evidence: `backend/src/aiobs_backend/api/deps.py:53-59` ("No auth is required for reads in
v1", project scope is just a header echo); `main.py:57-62` `allow_origins=["*"]`;
`docker-compose.yml` ships `AIOBS_ADMIN_API_KEY: admin` and `postgres/postgres`; admin key
compared with `!=` (`deps.py:25`). Verified live: anonymous reads succeed, CORS `*`.
Why it matters: contradictory to docs/04 §4.9; any page on the internet can read a dev's
localhost data and (with the default key) mint API keys.
Fix: require the project key or an admin/read token on all reads; CORS allowlist from
settings; force non-default secrets (`AIOBS_ADMIN_API_KEY` required, no default);
`hmac.compare_digest`.

---

**F07 [P1] Project scope is cosmetic and inconsistent; unvalidated header**
Evidence: `x-project-name` is unvalidated (`deps.py:53-59`); detail routes ignore it
(`routes/executions.py:48-113` — `GET /executions/{id}`, `/spans`, `/failures`); `/metrics`
and `/alerts` have no scope at all; omitting the header returns all projects.
Why it matters: contradictory to docs/04's shared-platform model — project A can read
project B's traces by id. Reviewers will call this the multi-tenancy trap.
Fix: validate the header against `projects` (and optionally the API key); enforce the
scope in every read query including detail/spans/failures/metrics/alerts; deny cross-scope
lookups. Document the v1 limitation honestly if full RBAC is out of scope.

---

**F08 [P1] Pricing history (`effective_from`) is ignored by the cost engine**
Evidence: `backend/src/aiobs_backend/cost.py:15,29-53` loads pricing rows and matches
exact/prefix/provider-default without filtering `effective_from <= at` (the constructor
stores `_at` but never uses it); the pricing API cannot even set `effective_from`
(`routes/pricing.py:17-26`). `plans/backend.md §8.3` and ticket 03 require effective-dated
resolution.
Why it matters: re-pricing after a change silently rewrites the cost of historical
executions; future prices apply today. Cost accuracy is the assignment's KPI 2.
Fix: filter by `effective_from` and order by `effective_from desc, match-kind`; add
`effective_from` to the API schema; test a price change between two executions.

---

**F09 [P1] Budgets never reset; utilization only grows**
Evidence: `Budget.period` is a single start timestamp (`models.py:246-248`);
`alerts.py:24-38` sums spend `WHERE started_at >= budget.period` with no upper bound;
no period type/end exists. `tests/test_ingest.py` enshrines a `period="2000-01-01"` budget.
Why it matters: a "monthly" budget accumulates forever and eventually alerts permanently,
inverting the feature's purpose (`CONTEXT.md`: "budget = configured spend cap **per
period**").
Fix: add `period_type` (`day|week|month`) + computed `period_end`; compute spend inside
the window; evaluate/reset per window; add rollover tests and scope budgets by
project/client.

---

**F10 [P1] Alert acknowledgement is an unauthenticated mutation**
Evidence: `backend/src/aiobs_backend/api/routes/alerts.py:52-57` — `PATCH /alerts/{id}` has
no admin dependency, unlike other mutating endpoints; CORS `*` makes it reachable from a
browser.
Fix: add the admin-key dependency and a test asserting 401 without it.

---

**F11 [P1] Pagination is in-memory and unstable; aggregations run in Python**
Evidence: `routes/executions.py:29-45` loads **all** matching executions, sorts in Python by
`started_at.isoformat()`, then slices — no SQL `ORDER BY/LIMIT/OFFSET`, no deterministic
tiebreaker, so pages can duplicate/skip as data changes. Same unbounded pattern in
`overview.py`, `workflows.py`, `clients.py`, `agents.py`, `costs.py`.
Why it matters: the first page over ~10k executions becomes slow and wrong; docs/04 expects
a shared platform.
Fix: SQL `ORDER BY started_at DESC, id` + `LIMIT/OFFSET` (keyset later); aggregate with
`GROUP BY`/`func.sum` in SQL; return totals for the UI.

---

**F12 [P1] Money is accumulated as floats, and unpriced calls silently become `$0`**
Evidence: `pipeline.py:188,226-289` sums Python floats into `Numeric(18,6)`;
`total_cost = sum if priced_calls else None` means a mixed priced/unpriced execution gets
a partial total with no warning; every aggregate converts `NULL→0`
(`analytics.py:70`, `overview.py:49`, `costs.py:88`, `clients.py:49`, `workflows.py:50`).
Verified live: 14/15 executions have `NULL` cost and `/costs` reports `client-42: 0.0`.
Why it matters: plan §5 mandates numeric money to avoid drift; unpriced spend disappearing
as `$0` misstates every FinOps number and undermines KPI 2.
Fix: use `Decimal` end-to-end; flag executions with unpriced calls
(`cost_complete`/`unpriced_calls`) and surface "unpriced" in APIs and the UI instead of
`0`; never fold `NULL` into a total without a caveat.

---

**F13 [P1] SDK export failures are silent and `flush()` lies**
Evidence: `_enrichment.py:109-121` returns FAILURE and the batch is dropped (BatchSpanProcessor
ignores the return); 401/404 (bad key/unknown project) fails immediately, logged only by
OTel (`_tracing.py:84-90`); `flush()` returns `force_flush()` (queue drained), not export
success (`__init__.py:89-99`).
Why it matters: a misconfigured app believes telemetry is flowing; the whole product is
silent when it matters most. `plans/sdk.md` promises "never break the app" *and* reliability.
Fix: track consecutive export failures in the enricher; expose `last_export_error`/counters;
log once at ERROR with remediation; make `flush()` return False when the last export failed;
add an `init()` self-test (auth header check) and a drop counter for queue overflow.

---

**F14 [P1] SDK buffers every span of a trace until the root ends**
Evidence: retry counting/root enrichment forces whole-trace buffering
(`_enrichment.py:40,104-160`); only trace *count* is capped (1000), not spans per trace;
nothing exports until the workflow ends. The plan specified an SDK-owned `SpanProcessor`
(`plans/sdk.md` §6.4) which can count without buffering.
Why it matters: long-running/streaming workflows hold all spans (and copies) in memory and
emit nothing until the end — the opposite of batch tracing, and a real OOM risk.
Fix: move retry/root logic into a `SpanProcessor` with per-trace counters + TTL; keep the
exporter streaming; cap spans per trace with an explicit overflow policy.

---

**F15 [P1] The frontend filter bar does not filter the data**
Evidence: `frontend/src/api/client.ts:43-45` never passes filters to `/metrics`;
`/alerts` and `/budgets/status` are fetched unfiltered (`Manager.tsx:23-25`,
`Executive.tsx:21`, `Overview.tsx:18`); the Engineering list sends `days` but the backend's
`/executions` has no `days` param (`executions.py:17-27`, silently ignored by FastAPI).
Why it matters: KPI cards are 30-day while the chart/forecast beside them is all-time; the
"days" selector misleads. `plans/frontend.md §5` promises filters threaded into every call.
Fix: pass `start/end` (computed from `days`) plus project/client/workflow into all queries;
add `days` (or `start/end`) to `/executions`; re-key queries on filter changes.

---

**F16 [P1] Personas are navigation links, not access control**
Evidence: `frontend/src/components/AppShell.tsx:48-68` — the "RoleSwitcher" renders three
`NavLink`s; no role state, no guards; all views are in the main nav; backend reads are
anonymous (F06). docs/04 §4.9 and docs/03 §3.13 expect role-differentiated access.
Fix: introduce a `role` in app state (persisted) that gates routes/panels, and back it with
at least project-key-authenticated reads; if real RBAC is out of scope for the assignment,
say so explicitly in the README/ADR instead of implying it works.

---

**F17 [P1] Postgres data is not persisted; no backup story**
Evidence: `docker-compose.yml:8-22` — no named volume for `/var/lib/postgresql/data`, no
`restart:` policy. `docker compose down` (or a recreate) loses platform + Phoenix data.
Fix: add a named volume + `restart: unless-stopped`; add a backup/restore section to the
README (`pg_dump`/restore commands); consider a nightly dump script.

---

**F18 [P1] API-key lifecycle is half-done**
Evidence: `routes/projects.py:27-81` supports list/create/rotate only; `Project.enabled`/
`revoked_at` exist (`models.py:49-53`) but nothing toggles them — no disable/revoke
endpoint despite `plans/backend.md §4.2` ("revoked keys reject ingest"); `seed.py:74-75`
returns the literal `"demo-key-not-returned-for-existing-project"` as if it were a key.
Fix: add disable/enable (and ideally `DELETE`) with tests proving revoked keys get 401 on
ingest; add `last_used_at`; fix the seed placeholder.

---

**F19 [P1] `json` instead of `jsonb`, and root `metadata` is stored unredacted**
Evidence: `models.py:8,111,159` use `json` (verified in Postgres; `plans/backend.md §5.2`
promises JSONB); `pipeline.py:176` copies the root `metadata` verbatim into an analytics
table, bypassing the redaction rules in `aiobs_contracts`.
Why it matters: no containment/index queries, larger storage, and business/PII context can
persist in cleartext despite the redaction contract (docs/04 §4.9).
Fix: migrate to `jsonb` (Alembic), apply `contracts` payload rules to `metadata` before
persistence, and add a test that sensitive keys are stripped.

---

**F20 [P1] Backend tests are thin and blind to every P0 above; migrations are decorative**
Evidence: only 3 test files / **17 tests** (`tests/`); no tests for re-ingest idempotency,
pricing dates, budget expiry, mixed priced/unpriced, `/agents` double counting, scope on
detail routes, malformed OTLP, or rollup races. Alembic exists but the image doesn't copy
`alembic/` (`backend/dev/Dockerfile:7-10`), startup uses `create_all()` (`main.py:38-45`),
and the live DB has no `alembic_version` — the migration is never exercised or provable.
CI has no lint/typecheck/coverage for Python (`backend.yml`).
Fix: add regression tests for F02/F08/F09/F12/F21; run `alembic upgrade head` on deploy and
add a CI job asserting `alembic check`/autogenerate is empty; add `ruff`, `mypy` (or
pyright) and a coverage floor.

---

**F21 [P1] Malformed OTLP → 500; no size/rate limits**
Evidence: `ingest/otlp.py:86-95` calls `ParseFromString` unguarded;
`routes/ingest.py:15-21` has no per-trace error isolation, body size cap, content-type
check, or rate limiting (docs/plan §4.3 requires structured rejection). One bad trace can
roll back a whole request.
Fix: catch `DecodeError` → 400 with structured detail; cap body size; per-trace savepoints;
per-project ingest quotas/rate limits; return the OTLP protobuf response.

---

**F22 [P1] Contract drift is still possible despite `aiobs_contracts`**
Evidence: `CONTEXT.md` says "never re-declare", yet constants are duplicated —
`_attributes.py:89` `CHAIN_KIND` vs `contracts.KIND_CHAIN`; hardcoded kind sets in
`_enrichment.py:194,208` and `_retries.py:33`; `"x-project-name"` duplicated in
`_tracing.py:32` vs `backend/api/deps.py:32`; dead `_SDK_HINTS`
(`backend/classify.py:16`); `openinference-semantic-conventions` declared but unimported;
`shared/**` is **not** in any workflow path filter, so contract changes merge green.
Fix: import all names from `aiobs_contracts`; add `shared/**` to `sdk.yml` and
`backend.yml` (and ideally one "contracts" job running both test suites); add a version
constant checked by both sides.

---

**F23 [P1] Frontend error/empty states are indistinguishable; several numbers mislead**
Evidence: no `isError` handling anywhere (`grep` empty); `AppShell.tsx:14` treats a failed
alert fetch as 0; `Overview.tsx:29-53` shows a zeros dashboard on error;
`ExecutionDetail.tsx:14` reports 500s as "not found". Also: budget utilization is clamped
for display (`Manager.tsx:90,98` → 250% shows "100%"); Overview colors decreases as "bad"
(`Overview.tsx:37-38,79-82`); Manager prints `error_rate` raw (`Manager.tsx:46`) while
Overview formats %; forecast silently disappears (`forecast.ts:12-13`) and is anchored to
the last data day, not today (`forecast.ts:27-29`).
Fix: add error banners + `retry` policy + an error boundary; clamp only the bar width, show
true %; direction-aware tone per metric; use `formatPct`; show "insufficient data" for the
forecast and anchor to today with the window stated.

---

**F24 [P1] Promised UI features are missing**
Evidence: `useAgents` exists but is imported nowhere (`api/hooks.ts:51`); "Failure tree" is
a flat list ignoring `parent_id` (`ExecutionDetail.tsx:87-101`); no chart→executions
drill-down; Engineering hardcodes `limit=100` and ignores `total` (`client.ts:34`); no
status-filter UI though the hook supports it; alert ack/close actions absent; unpriced has
no badge (`format.ts` maps `null` → "—"); no refetch interval/manual refresh
(`main.tsx:9` staleTime only).
Fix: render the agents panel (`/agents`), make `FailureTree` hierarchical + link to spans,
paginate the executions table, add the status filter + alert actions, add an
"unpriced" chip, and add a modest `refetchInterval` (or refresh button).

---

**F25 [P1] Attribution gaps: no team/service rollup; agents are global; `/agents` double counts**
Evidence: analytics dimensions are `total|project|client|workflow` only (`analytics.py:17`);
docs/03 §3.10 / plan §8.2 want team (and service); `agents.name` is globally unique
(`models.py:81-87`) so same-named agents from different projects collapse; `/agents`
adds `ex.total_cost`/`total_tokens` for **every** AGENT span of the same execution
(`routes/agents.py:40-49`) → double-counted cost and `error_rate` can exceed 1.
Fix: make agents project-scoped; aggregate per execution (distinct) or sum span costs;
add a `team` dimension via `projects.team_id` and a team cost endpoint; render the agents
panel in Manager.

### P2 — should fix before calling it done

---

**F26 [P2] `daily_metrics` has no unique key and is rebuilt by delete+reinsert**
Evidence: `models.py:229-231` index is non-unique; `analytics.py:62-64,79-98` deletes and
re-inserts; the 60s background loop (`main.py:25-35`) and admin rollup can interleave →
duplicate metric rows inflate every chart; no test catches it.
Fix: unique constraint on `(day, dimension, dimension_key)` + `ON CONFLICT DO UPDATE`;
evaluate rollup per day transactionally.

---

**F27 [P2] Concurrent re-ingest races raise IntegrityError and roll back whole requests**
Evidence: delete-then-insert with unique `executions.trace_id` (`pipeline.py:127-136`),
select-then-insert upserts (`pipeline.py:305-354`); two exporters re-sending the same trace
can collide; ingest has no per-trace isolation.
Fix: `INSERT … ON CONFLICT DO UPDATE` for executions/clients/workflows/agents; per-trace
savepoints; unique constraints on `(project_id, name, version)`; concurrency test.

---

**F28 [P2] Root failure kind can mask a more precise child failure**
Evidence: `pipeline.py:272-276` unconditionally prefers the root's kind; a root without
`sdk.error.kind` classifies as `business_logic`, overwriting a child `rate_limit`/`timeout`
(see the comment in `kpi_gate.py:142-143`). docs/03 expects the most specific failure.
Fix: pick the earliest failing descendant (by hierarchy/start time), fall back to the root;
test wrapper-rooted failures.

---

**F29 [P2] Cache-token pricing math can go negative and fabricates a rate**
Evidence: `cost.py:69-77` — `input_tokens - cache_read - cache_write` is unclamped (can be
negative for providers where `input_tokens` already excludes cache tokens), and
`cache_write_price_per_1m is None` invents `input × 1.25`, contradicting "unpriced → NULL,
never fabricated" (CONTEXT.md / ticket 03). The SDK never emits `prompt_details.*`, so this
path is only exercised by synthetic tests.
Fix: clamp at zero; follow provider semantics from the contract; treat missing cache
prices as unpriced (NULL + flag) rather than inventing rates; add tests per provider shape.

---

**F30 [P2] Deleting a price orphans historical cost records**
Evidence: `routes/pricing.py:72-79` hard-deletes; `models.py:204` `cost_records.price_version`
stores `pricing.id` with no FK and no denormalized rates — audits and re-costing break.
Fix: soft-delete/deactivate with `effective_to`; snapshot the resolved rates on the cost
record; add an FK or keep the row forever.

---

**F31 [P2] API time filters have inconsistent timezone semantics**
Evidence: `api/queries.py:14-28` — `%Y-%m-%dT%H:%M`/`:…:%S` parse to **naive** datetimes
(bound as session-local), while the date-only branch assumes UTC and `default_range` is
aware UTC; `start=2026-09-15T10:00:00` can shift by the server offset; unknown formats
return `None` silently.
Fix: parse all branches as aware UTC (assume UTC when no offset); return 422 on invalid
input instead of silently ignoring.

---

**F32 [P2] API contract nits**
Evidence: invalid `dimension` returns `200 {"detail":…}` (`costs.py:32-33`,
`metrics.py:24-25`) instead of 4xx; budgets list exposes internal IDs while every other
resource uses external keys (`budgets.py:56-60`); `POST /metrics/rollup` reports
`days=len(counts)` — metric rows, not days (`maintenance.py:15-17`); `_percentile`
duplicated (`overview.py:18-28`, `analytics.py:20-30`); nanosecond→datetime via float64
loses sub-µs precision (`otlp.py:55-58`).
Fix: 422 on bad enums; external keys in budget responses; correct the rollup summary;
single `_percentile`; integer arithmetic for timestamps.

---

**F33 [P2] Token backfill can fabricate usage without marking it**
Evidence: `sdk/src/ai_observability/_usage.py:100-186` estimates missing counts (tiktoken
opt-in or chars/4) and emits them like real data; docs/05 §5.3 cost accuracy assumes honest
tokens. No `estimated` flag exists.
Fix: stamp `sdk.tokens.estimated=true` on backfilled spans; surface "estimated" in cost
views; document the limitation in docs/05 context.

---

**F34 [P2] Manual-vs-agent cost comparison / margin is missing**
Evidence: docs/01 §1.1 and §1.4, docs/03 §3.13 ask for cost vs manual process and potential
margin; no manual-cost or revenue concept exists anywhere (`revenue`, `manual cost` greps
empty); Executive shows cost per client instead of cost per service (docs/03 §3.10 lists
them separately).
Fix: either implement a minimal manual-cost/revenue field per workflow/client and a margin
KPI, or explicitly descope with an ADR so the docs and app agree.

---

**F35 [P2] Retention, deletion and PII posture are undefined**
Evidence: payload stripping exists at export/persist (`_enrichment.py:69-72`,
`pipeline.py:30-32`) but there is no retention/TTL, no erasure path, no PII ADR; docs/04
§4.9 requires minimization/handling.
Fix: add retention windows + purge job; document the payload/redaction model in an ADR
(encryption at rest/in transit, deletion procedure).

---

**F36 [P2] No Kubernetes deployment (or explicit descope)**
Evidence: docs/04 §4.7/§4.8 show a K8s layout; only Docker Compose exists
(`.scratch/backend/map.md:46` lists it as fog).
Fix: add minimal manifests (Deployments/StatefulSet + Service + Secret + probes) or write
an ADR that downgrades §4.7 to "compose for the prototype" with rationale.

---

**F37 [P2] Alerts have no delivery channel**
Evidence: alerts only exist as DB rows + UI badge (`alerts.py`, `/alerts`); no
email/Slack/webhook anywhere, though docs/04 §4.4.7 describes an alert engine and
`CONTEXT.md` calls alerts "open notifications".
Fix: add a pluggable notifier (at minimum a webhook) and document it; or state explicitly
that the platform only exposes alerts via API/UI in v1.

---

**F38 [P2] CI hardening**
Evidence: `sdk.yml` e2e runs only on `push` (not PRs); `backend.yml` KPI job depends on
`sdk/`+`shared/` but isn't triggered by them; no coverage anywhere; no Python
lint/typecheck; `e2e_smoke.py` is orphaned (no workflow); `arizephoenix/phoenix:latest` is
unpinned; no job timeouts; no frontend↔live-backend smoke.
Fix: pr-triggered e2e with a pinned Phoenix image; add `shared/**`/`sdk/**` to backend KPI
paths; run `e2e_smoke.py` in a compose integration job; coverage floors; `ruff` + `mypy`;
`timeout-minutes` on all jobs.

### P3 — polish

---

**F39 [P3] SDK seams and hygiene**
Evidence: unknown `init()` kwargs are silently ignored (`__init__.py:55,74`) — a typo like
`init(project="x")` silently produces 401-dropped traces; an endpoint already ending in
`/v1/traces` becomes `/v1/traces/v1/traces` (`_tracing.py:86`); `register_span_kind_override`
mutates a list without a lock while the export thread iterates (`_enrichment.py:45-50`);
`atexit` is registered only for the first provider (`_tracing.py:126-141`); dead code/dupes
(`_SDK_HINTS`, `CHAIN_KIND`, unused semconv dependency).
Fix: reject unknown kwargs, normalize endpoint paths, validate key/project at init, lock
the hook registry, register atexit per provider, delete dead constants.

---

**F40 [P3] Frontend polish and test infrastructure**
Evidence: `formatMoney` prints `$1234.5000` (no grouping, 4dp; `format.ts:1-4`); no
`flex-wrap`/table `overflow-x` → mobile overflow; Recharts/tables lack a11y labels
(`scope`/`caption`); nginx has no gzip/cache headers (`frontend/dev/nginx.conf`); no ESLint;
Vitest is `environment: "node"` with only 2 lib test files, no component/route tests, no
coverage provider, no Playwright.
Fix: fix money formatting (2dp `en-US`), responsive pass, a11y pass, gzip/cache headers,
add ESLint + RTL component smoke tests + one Playwright happy path per role.

---

**F41 [P3] Docs drift vs implementation**
Evidence: `plans/sdk.md` still promises background-worker mode and cache/reasoning token
validation (not implemented); `plans/frontend.md` promises pagination/drill-down not built;
`plans/backend.md §10` lists alert rules the code doesn't have (related to F04);
`.scratch/sdk/*` describe redaction as "deferred" while export-time stripping shipped.
Fix: mark deferred items explicitly in the plans (or implement F04/F24), and make the
README's status table the single source of truth.

---

## 6. Prioritized fix roadmap

1. **F01** (one-line backend or frontend change) + a contract test + OpenAPI codegen —
   restores the FinOps demo.
2. **F03** guard the destructive KPI script, then **F05/F04** make the KPI gate and alert
   engine actually match docs/05 (this is what the assignment is graded on).
3. **F02** fix partial-batch ingest + regression tests (data integrity).
4. **F06/F07/F10/F16/F17** security/tenancy/persistence baseline (auth on reads, scope
   enforcement, admin on alert acks, Postgres volume).
5. **F08/F09/F12** cost and budget correctness (pricing dates, budget windows,
   Decimal + unpriced surfacing).
6. **F11/F26** SQL pagination/aggregation + metric upserts (scales past the demo).
7. **F13/F14** SDK reliability (fail-loud exports, SpanProcessor enrichment).
8. **F15/F23/F24/F25** frontend truthfulness and missing panels (filters, errors, agent
   efficiency, failure tree, pagination).
9. **F18/F19/F20/F21/F22/F38** lifecycle, JSONB/redaction, tests/migrations/lint, ingest
   hardening, contract CI.
10. **F34/F35/F36/F37/F41** decide and document (margin, retention, K8s, alert delivery,
    doc drift) — implement or descope explicitly.

Each P0/P1 finding above is independently shippable; none requires redesigning the
architecture, which is the good news: the core (contract-driven pipeline, deterministic
mock scenarios, KPI harness) is the right skeleton to build the fixes on.

---

## 7. Implementation status (post-audit)

Work in `feat/backend-frontend-plans` (uncommitted at time of writing).
Verification: **56 backend tests pass** (was 17), the **hardened KPI gate passes 14/14**
with measured KPI values, and each fix was re-verified against the live Docker stack.

### Fixed (with tests)

| ID | Fix |
|---|---|
| F01 | `/costs` now returns `total_cost` for every dimension (+ contract test, live-verified) |
| F02 | Partial/children-only batches merge into the existing execution; rows are never deleted before root validation (+ 4 regression tests: merge, skip, mismatch-preserves, bogus-root) |
| F03 | `kpi_gate.py` refuses non-disposable DBs (defaults to `aiobs_test`; `AIOBS_KPI_ALLOW_RESET=1` override) + guard tests |
| F04 | Threshold alert rules: error rate, daily tokens, tool calls/execution, p95 latency, cost vs 7-day moving average (+ 5 tests; KPI gate now asserts a non-budget alert) |
| F05 | KPI gate measures docs/05: span coverage (100.0%), cost error (0.0000%), client/workflow attribution, 5 failure kinds, alert scenario |
| F07 | `x-project-name` is validated against registered projects; detail/spans/failures and metrics honor the scope (404 outside it) (+ tests) |
| F08 | `effective_from` gates pricing resolution; pricing API accepts it (+ 3 history tests) |
| F09 | Budgets have `period_type` (day/week/month) and windowed spend/reset; utilization never clamped in the API (+ 5 tests) |
| F10 | `PATCH /alerts/{id}` requires the admin key (+ test, live 401 verified) |
| F17 | Postgres data persists in a named volume; all services `restart: unless-stopped` |
| F18 | `POST /projects/{id}/disable|enable` revokes/restores keys; disabled projects 403 on ingest (+ tests, live-verified) |
| F21 | Malformed OTLP → 400, oversized bodies → 413, per-trace savepoints keep the rest of the batch (+ 3 tests) |
| F22 | `shared/**` changes now trigger the backend and SDK workflows |
| F24 | Manager has an agent-efficiency panel; the failure tree is rendered hierarchically |
| F28 | Execution root cause prefers the most specific failing descendant (+ test) |
| F29 | Cache pricing never fabricates rates and cannot go negative; missing cache prices stay unpriced (+ 5 tests) |
| F31 | Naive API timestamps are interpreted as UTC |

### Partially fixed

| ID | Done | Remaining |
|---|---|---|
| F06 | Read auth dependency: when `AIOBS_READ_API_KEY` is set, every read endpoint requires `x-api-key` (or the admin key) + tests | Not enforced by default (demo); no per-user identities |
| F11 | `/executions` uses SQL `ORDER BY started_at DESC, id` + SQL count/limit/offset | workflows/clients/agents/costs still aggregate in Python |
| F12 | `unpriced_calls` + `cost_complete` surfaced on executions | `Decimal` end-to-end; aggregates still fold NULL to 0 |
| F15 | `days` supported by `/executions` and `/metrics`; dashboard trends/forecast/metrics now filtered | alerts/budget panels are intentionally global |
| F16 | Role selector gates nav links and routes (persisted in localStorage), documented as presentation-level | No server-side RBAC (needs F06 + identities) |
| F20 | 17 → 56 tests covering every P0 | lint/typecheck/coverage, Alembic in deploy/CI |
| F23 | Budget % displayed unclamped, `formatPct` for error rate, direction-aware deltas | error banners, forecast labeling/anchor |
| F32 | Invalid `dimension` returns 422 | budget response keys, rollup summary, percentile de-dup |

### Not started (next waves)

F13/F14 (SDK fail-loud exports, SpanProcessor enrichment), F19 (JSONB + metadata
redaction), F25 (team/service attribution, `/agents` double count), F26/F27 (rollup
uniqueness, concurrency), F30 (price deletion), F33–F41 (retention, K8s, alert delivery,
CI hardening, docs drift).

