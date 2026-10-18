# 04 — Backend: `loop_executions` alert metric

Type: task
Status: resolved
Blocked by: 03
Area: loop detection, alerting
Estimate: M

## Comments

- 2026-10-17: `loop_executions` metric (day-scoped, scope-aware),
  `alert_loop_executions = 5` setting, seeded built-in "Looped executions"
  (warning ×1, critical ×2), route whitelist, `_fmt_value` rendering.
  Existing builtin-count assertions updated 5 → 6; new alert test asserts the
  warning fires once and dedupes.

## Goal

Alert when looped executions accumulate, using the existing rule engine
(thresholds over a window, dedupe, channels, 60 s evaluation loop).

## Changes

1. `alerts.py` — add `loop_executions` to `METRICS`; evaluation branch: count
   executions with `loop_detected` in the rule window (global / project /
   workflow / agent scope like the other metrics).
2. `config.py` — `alert_loop_executions: float = 5` (confirms the built-in).
3. `seed.py` — seeded built-in rule "Looped executions" (warning = env value,
   critical = 2×).
4. `api/routes/alert_rules.py` — whitelist the new metric.
5. `models.py` — extend the `AlertRule.metric` comment.
6. Tests: rule trips at warning/critical, dedupes across evaluations, respects
   scope, disabled rule stays silent.
