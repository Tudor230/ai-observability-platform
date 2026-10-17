# ADR-0013: Revenue and manual-cost inputs; margin in the Executive view

Status: Accepted (2026-10-16) — amends [ADR-0005](0005-margin-descope.md)

## Context

ADR-0005 descoped margin and manual-vs-agent comparison because the required
inputs — what a task is worth (revenue) and what a human would cost — are
customer business data, not telemetry, and inventing defaults would produce a
margin number that looks authoritative but is fiction.

The product decision has changed: the executive view must show **margin**. The
resolution is not to infer the missing inputs but to make them explicit,
exec-maintained configuration — exactly the additive path ADR-0005 sketched
("two configuration tables + one KPI, no pipeline changes").

## Decision

- **Rates are versioned run-rates.** Each version carries an explicit
  `effective_from` chosen by the exec; the active rate for a day is the row with
  the greatest `effective_from <= day`. New versions never overwrite older ones
  (`UNIQUE (project_id, effective_from)`, a clash is a `409`), and existing
  versions are editable and deletable. Revenue accrual therefore shows a mid-
  window price change as a step rather than rewriting history.
- **Inputs per version**: revenue amount + period (`month`|`year`) and an
  **optional** manual cost amount + period. Unset manual cost means 0 and is
  flagged as unset in the UI (it is not the same fact as "zero").
- **Margin** = prorated revenue − prorated manual cost − AI cost. Proration is
  per day (`month ≡ 365/12 days`, `year ≡ 365`), so any window length works.
- **Totals are conservative for external work**: every external project's AI
  cost counts, including days with no active rate. Internal projects are the
  deliberate exception (above). Coverage is reported beside the totals —
  external projects with an active version, and the share of external AI cost
  on covered days — and rows without a rate show *no margin* rather than `$0`,
  so a partially filled rate book is visible instead of silently reading as a
  loss.
- **Internal projects need no revenue.** A project can be flagged *internal*
  (`projects.internal`): it serves the org itself (tooling, R&D, demos), so its
  AI cost is reported as *internal spend* — separately from the margin totals
  and outside the coverage percentage — instead of reading as a loss. The flag
  wins over any rate versions the project may have.
- **Break-even scale** = `(revenue − manual cost) ÷ AI cost`: the multiple of
  current volume whose AI cost consumes the contribution. Forward-looking
  figures use the version active on the window's last day.
- **Access**: margin reads and rate writes are exec/admin only; the admin key
  bypasses the role check as elsewhere. Managers keep cost-only views.
- The platform never invents a manual-cost or revenue default; manual cost
  remains an input, and the UI labels every margin figure as derived from the
  entered rates.

## Consequences

- The Executive view shows margin, break-even and a scaling scenario without
  fabricating business data, and internal work never distorts it.
- Rate history is auditable (who/when) and price changes are non-destructive.
- A partially filled rate book yields a low coverage percentage — the signal
  that keeps a conservative total from being misread as a loss.
- `plans/roles.md` gains the `project-rates` / `margin` rows; `/costs` keeps its
  existing gate.
