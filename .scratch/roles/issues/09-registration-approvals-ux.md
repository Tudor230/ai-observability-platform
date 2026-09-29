# 09 — Registration & approvals UX

Type: prototype
Status: resolved
Blocked by: 05, 08

## Question

How should the request + approval screens look and behave?

Build a rough UI stub to react to:
- Request forms: register a department / team / project, and request a
  membership/role.
- The manager approval inbox: approve / reject + reason.
- The requester's request-status list.

Link the prototype as an asset on resolution.

## Answer

Prototype: [prototypes/09-registration-approvals.html](../prototypes/09-registration-approvals.html)
(rough dark-theme stub for discussion; not production code).

- **Layout**: one `Requests` page with three tabs — New request / Approvals /
  My requests.
- **Nav**: a single `Requests` nav item for all authenticated users (added to
  08's route map); the Approvals tab carries a pending-count badge for users
  who cover requests.
- **Request forms**: a type picker (Department / Team / Project / Membership).
  The membership form is **role-first**: scope options filter to valid scopes
  (engineer → team, client → project, manager → team or department). The form
  previews who will review the request.
- **Approvals**: rows show type, summary, requester, scope, age; **Approve**
  is one-click; **Reject opens a modal with a required reason**. Managers see
  only requests their memberships cover; admin/exec get an "All requests"
  filter.
- **My requests**: status list with cancel (pending) and resubmit (rejected);
  the rejection reason is shown.
- **Project key minting**: lives on a **project page** (a new surface,
  reachable from the request), not the request row — "Mint API key", plaintext
  shown once.
- Implementation notes: no dialog component exists in the frontend today
  (research 02) — the reject modal introduces one; the project page is a new
  route.