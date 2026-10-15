# 01 — Docs: ADR-0011/0012, v3 spec, glossary

Type: task
Status: resolved
Blocked by: —
Area: refinements v3, phase 0
Estimate: S

## Goal

Land the decisions before the code: the two ADRs, the v3 spec and tickets, and
the `CONTEXT.md` glossary entries that the rest of the effort cites.

## Changes

1. `docs/adr/0011-retire-client-attribution-dimension.md` — the client data
   dimension is retired; the RBAC `client` role is explicitly out of scope.
2. `docs/adr/0012-generated-project-identifiers.md` — generated
   `p_<hex>` ids, name as the unique handle, debug-only SDK override.
3. `.scratch/refinements-v3/spec.md` + `issues/01..12` — this spec and the
   ticket set.
4. `CONTEXT.md` — glossary:
   - **Workflow root**: drop `sdk.client_id`; `sdk.project_id` becomes
     debug-only/optional (server-authoritative stays).
   - **Attribution dimensions**: `project, workflow, agent, team` (client
     removed).
   - **OTLP ingest**: `x-project-name` described as debug routing.
   - Add **Project name** (unique human handle) and **Generated project id**
     (`p_<hex>`, internal/technical token, never rendered) entries, plus the
     explicit note that the **client role** is a membership, unrelated to the
     retired client dimension.

## Acceptance

- Every decision from the planning session (`.scratch/refinements-v3/spec.md`
  "Settled decisions") has the ADR/spec/glossary line that carries it.
- No doc promises `project_name` or a client dimension anywhere.

## Tests

- Review only; `git grep -n client_id CONTEXT.md` returns nothing.

## Comments

Done. Landed `docs/adr/0011-retire-client-attribution-dimension.md`,
`docs/adr/0012-generated-project-identifiers.md`, `.scratch/refinements-v3/`
(spec + tickets 01–12) and the `CONTEXT.md` glossary updates: the workflow root
loses `sdk.client_id` (project id debug-only), attribution dimensions become
project/workflow/agent/team, new **Project name** / **Generated project id**
entries, and the **Client role** entry states the role is unrelated to the
retired dimension. `git grep -n client_id CONTEXT.md` → no matches.
