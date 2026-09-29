# 05 — Request & approval semantics

Type: grilling
Status: resolved
Blocked by: 03

## Question

What is the full semantics of the approval workflow?

Settled constraints (from charting): any authenticated user submits self-service
requests; entity creation (department/team/project) AND membership changes both
route through manager approval; manager assignments + a new department's
nominated manager are approved by admin/exec only; approver = any manager whose
membership covers the target scope, else admin/exec.

Decide:
- The `requests` table: `type` enum + payload shapes (`create_department` incl.
  nominated manager, `create_team`, `create_project`, `membership`), requester,
  status, approver, reason, timestamps.
- Status lifecycle: `pending → approved | rejected`, re-submission, dedupe of
  open duplicate requests.
- The approver-resolution algorithm for each request type under flexible
  manager assignment.
- Materialization handlers on approval (create entity / approve membership).

## Answer

Decided:

- **One `requests` table holds all pending state.** Columns: `id`, `type`,
  `requester_id` (FK → users), `payload` (JSONB), `status`, `approver_id`,
  `reason`, `created_at`, `decided_at`.
- **Types + payloads**:
  - `create_department`: `{name}` — **the requester becomes the department's
    initial manager** on approval.
  - `create_team`: `{name, department_id}`
  - `create_project`: `{project_id, name, team_id}`
  - `membership`: `{role, scope_type, scope_id}` (self-join: user = requester;
    manager-role requests are admin/exec-approved).
- **Approver resolution — scope-covering managers**: `create_department` and
  manager-role membership requests → **admin/exec only**; all other requests →
  any manager whose approved membership covers the target (department target →
  managers of that department; team/project target → that team's manager or its
  department's manager), plus admin/exec always.
- **Lifecycle**: `pending → approved | rejected` (+ requester can cancel); at
  most one pending per `(requester, type, payload)`; rejected may be
  resubmitted as a new request; approval re-checks uniqueness and fails cleanly
  with a reason; **rejection reason required**.
- **Materialization on approval**: create the department **and grant the
  requester an approved department-scoped manager membership (initial
  manager)**; create the team (**no manager nomination** — the department
  manager covers it); create the project (no key); or create an approved
  membership.
- **Multiple managers per scope**: several users may hold manager memberships
  on the same department; a manager may cover one or several teams (team-scoped
  memberships) or the whole department (department-scoped).
- **Project key**: after approval, **any member of the project** (i.e. an
  approved membership covering it) can mint/rotate via the existing endpoint;
  plaintext shown once. Read-only **clients are excluded** (refined by 10).
- **Refines 03**: memberships are only created on approval, so
  `memberships.status` is `approved|revoked` (no pending value).