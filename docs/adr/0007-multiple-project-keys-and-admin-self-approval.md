# ADR-0007: Multiple project ingest keys, self-approval, and admin account overrides

Status: Accepted

## Context

ADR-0006 shipped project ingest with a **single** credential
(`projects.api_key_hash`): rotating replaced it for every consumer at once, and
there was no way to see or revoke individual credentials. Requests always
queued for approval even when the requester already had the authority to
approve them (an admin creating a department, a manager creating a team in
their own department), adding a pointless wait. Admin account tooling was
limited to creating an identity; memberships could only be granted by approving
a request, and there was no password-reset path. Projects were only reachable
from the Requests page, with no per-project overview.

## Decision

- **A project has many ingest keys.** New `project_keys` table
  (`project_id`, `key_hash`, `key_hint`, `label`, `created_by`, `created_at`,
  `last_used_at`, `revoked_at`) replaces `projects.api_key_hash` /
  `api_key_label`; the migration carries existing hashes over. Ingest
  (`x-project-name` + `Bearer`) authenticates against **any active key** and
  records `last_used_at` on the matched row. The SDK contract is unchanged.
- **Keys are managed per credential**, member-authorized (covering
  engineer/manager) or admin: list (redacted `••••<hint>`), add (plaintext shown
  once), rotate (regenerate one key's secret in place, keeping its label), and
  **soft-revoke** (the row stays for audit; revoked keys stop authenticating and
  cannot be rotated).
- **Self-approval materializes immediately.** When the requester can approve
  their own request (`_can_approve`), `POST /requests` approves and materializes
  it in the same transaction instead of queueing it: admins create departments,
  covering managers create teams/projects, and covering managers can add
  memberships. Requests the requester cannot approve queue as before.
- **Admin account overrides.** Admins can provision accounts (password shown
  once), reset passwords (bumps `token_version`, revoking sessions), and
  **grant or revoke memberships directly**, bypassing the request flow.
- **Separate Projects page** (`/projects`) with a per-project overview and key
  operations, plus an admin-only **Accounts** page (`/accounts`); Requests links
  into projects but no longer hosts them.

## Consequences

- Multiple keys allow zero-downtime rotation (add new, migrate consumers,
  revoke old) and per-environment labels; revocation is granular and auditable.
- Ingest does one extra query (active keys for the project) and a best-effort
  `last_used_at` update per batch.
- Self-approval removes queue latency for already-authorized actors and leaves
  no pending row; `approver_id` equals the requester, so the audit trail still
  records who decided.
- Direct admin grants/revocations bypass the request trail
  (`requested_by`/`approver_id` are NULL in the memberships row), recorded via
  `decided_at`; the request flow remains the normal path.
- Soft-revoked keys accumulate; they are listed as revoked and can be cleaned
  up by a future retention job.

## References

- `plans/roles.md` — implementation plan
- `.scratch/roles/map.md` — the roles decision map
- `docs/adr/0006-membership-rbac-jwt-sessions.md` — the base RBAC/auth design
