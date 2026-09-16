# 02 — Routing & shell

Type: task
Status: resolved

## Question

How is the app structured around roles and filters?

## Answer

AppShell renders nav + a role switcher (Engineer / SDM / Finance) linking to
the three views, and a global filter bar (days, project, client, workflow)
lifted into a FiltersProvider context. All view queries key on the filters, so
changing them refetches everywhere.
