import type { DayMetric, FailureSeriesItem, ModelInsight, ToolInsight } from "../api/types";

/**
 * Series mappers for the insight charts (phoenix insights): one place turns the
 * API shapes into chart-ready rows so Overview, Manager and Executive render
 * exactly the same data the same way.
 *
 * These are `type` aliases, not interfaces, so the rows stay assignable to
 * `TrendChart`'s `Record<string, unknown>[]` prop.
 */

export type InsightPoint = {
  day: string;
  cost: number;
  executions: number;
  ok: number;
  failed: number;
  input_tokens: number;
  output_tokens: number;
  llm_calls: number;
  tool_calls: number;
  error_rate: number;
  cost_per_execution: number;
  p50_duration_ms: number;
  p95_duration_ms: number;
  p99_duration_ms: number;
};

/** Day metrics → per-day chart rows (traffic, tokens, latency, cost). */
export function dayMetricsToSeries(items: DayMetric[] | undefined): InsightPoint[] {
  return (items ?? []).map((m) => ({
    day: m.day.slice(5),
    cost: m.total_cost ?? 0,
    executions: m.executions,
    ok: Math.max(0, m.executions - m.failed_executions),
    failed: m.failed_executions,
    input_tokens: m.input_tokens,
    output_tokens: m.output_tokens,
    llm_calls: m.llm_calls,
    tool_calls: m.tool_calls,
    error_rate: m.error_rate,
    cost_per_execution: m.executions ? (m.total_cost ?? 0) / m.executions : 0,
    p50_duration_ms: m.p50_duration_ms,
    p95_duration_ms: m.p95_duration_ms,
    p99_duration_ms: m.p99_duration_ms,
  }));
}

export type FailureRow = { day: string; [kind: string]: string | number };

/** Failure counts by day × kind → rows for the stacked "Failures by kind" bars. */
export function failureRows(items: FailureSeriesItem[] | undefined): FailureRow[] {
  const byDay = new Map<string, FailureRow>();
  for (const item of items ?? []) {
    const row = byDay.get(item.day) ?? { day: item.day.slice(5) };
    row[item.kind] = Number(row[item.kind] ?? 0) + item.count;
    byDay.set(item.day, row);
  }
  return Array.from(byDay.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([, row]) => row);
}

export type ModelRow = {
  label: string;
  cost: number;
  tokens: number;
  input_tokens: number;
  output_tokens: number;
  calls: number;
  failed: number;
  error_rate: number;
  avg_duration_ms: number;
  p95_duration_ms: number;
};

export function modelRows(items: ModelInsight[] | undefined): ModelRow[] {
  return (items ?? []).map((m) => ({
    label: [m.provider, m.model].filter(Boolean).join(" · ") || m.key,
    cost: m.total_cost ?? 0,
    tokens: m.total_tokens,
    input_tokens: m.input_tokens,
    output_tokens: m.output_tokens,
    calls: m.calls,
    failed: m.failed_calls,
    error_rate: m.error_rate,
    avg_duration_ms: m.avg_duration_ms,
    p95_duration_ms: m.p95_duration_ms,
  }));
}

export type ToolRow = {
  label: string;
  calls: number;
  ok: number;
  failed: number;
  error_rate: number;
  avg_duration_ms: number;
  p95_duration_ms: number;
};

export function toolRows(items: ToolInsight[] | undefined): ToolRow[] {
  return (items ?? []).map((t) => ({
    label: t.name,
    calls: t.calls,
    ok: Math.max(0, t.calls - t.failed_calls),
    failed: t.failed_calls,
    error_rate: t.error_rate,
    avg_duration_ms: t.avg_duration_ms,
    p95_duration_ms: t.p95_duration_ms,
  }));
}

/** The top `limit` rows by one numeric field, largest first (stable). */
export function topBy<T extends Record<string, unknown>>(
  rows: T[],
  key: keyof T & string,
  limit = 8
): T[] {
  return [...rows]
    .sort((a, b) => Number(b[key] ?? 0) - Number(a[key] ?? 0))
    .slice(0, limit);
}
