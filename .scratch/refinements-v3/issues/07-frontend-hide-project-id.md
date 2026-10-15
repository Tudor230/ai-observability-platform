# 07 — Frontend: stop rendering `project_id`

Type: task
Status: open
Blocked by: 02
Area: refinements v3, project identity (ADR-0012)
Estimate: M

## Goal

The dashboard never shows a project id again: names everywhere, ids kept only
as technical tokens in URLs and payloads.

## Changes

1. **Render sites** (from the survey):
   - `pages/Project.tsx` — title becomes the name; delete the `project_id`
     `kv` row; keep the route param as the technical token.
   - `pages/Projects.tsx` — table cell shows the name; link target unchanged.
   - `components/FiltersControl.tsx` — project option label = name (value
     stays `project_id`); chip label = `Project: <name>`.
   - `components/BudgetDialog.tsx`, `pages/Accounts.tsx`, `pages/Alerts.tsx`
     — picker labels drop `project_id · `.
   - `pages/ExecutionDetail.tsx` — `project {ex.project_id}` becomes the
     project name from the new `project_name` payload field.
   - `pages/Engineering.tsx` — the client column is dropped here per ticket 08;
     the project column switches to `project_name`.
   - `lib/traceSpans.ts` — agent description uses `project_name`.
2. **Create-project form** (`pages/Requests.tsx`) — remove the slug input;
   payload becomes `{name, team_id}`; rename the local state
   (`projectSlug`/`projectName` → `projectName`); request summary text shows
   the name only.
3. **Types** — `types.ts` `Execution` gains `project_name`; `Project` keeps
   `project_id` + `name` (both still used by the API layer); drop any
   now-unused display helpers.
4. **Tests** — `pages.test.tsx` / `App.test.tsx` fixtures gain `project_name`
   and lose slug assertions; add a regression assert that no `p_`-style id is
   rendered on Project/Projects/Requests pages.

## Acceptance

- No page, table, chip, picker or dialog displays a raw project id; the URL and
  query params are unchanged.
- Creating a project needs a name only, and shows the name everywhere after
  approval.

## Tests

- `npm run test` (vitest + coverage gate), `npm run lint`, `npm run build`.
