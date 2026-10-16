import { describe, expect, it } from "vitest";
import type { DayMetric, ModelInsight, ToolInsight } from "../../api/types";
import {
  dayMetricsToSeries,
  failureRows,
  modelRows,
  toolRows,
  topBy,
} from "../insightSeries";

const metric: DayMetric = {
  day: "2026-10-01",
  dimension: "total",
  dimension_key: null,
  executions: 10,
  failed_executions: 2,
  error_rate: 0.2,
  total_tokens: 1000,
  input_tokens: 600,
  output_tokens: 400,
  llm_calls: 8,
  tool_calls: 3,
  total_cost: 0.5,
  avg_duration_ms: 100,
  p50_duration_ms: 90,
  p95_duration_ms: 300,
  p99_duration_ms: 500,
};

const model: ModelInsight = {
  key: "openai:gpt-4o-mini",
  provider: "openai",
  model: "gpt-4o-mini",
  calls: 4,
  executions: 3,
  failed_calls: 1,
  error_rate: 0.25,
  total_cost: 0.002,
  input_tokens: 600,
  output_tokens: 400,
  total_tokens: 1000,
  avg_duration_ms: 120,
  p95_duration_ms: 300,
};

const tool: ToolInsight = {
  name: "search",
  calls: 5,
  executions: 2,
  failed_calls: 1,
  error_rate: 0.2,
  avg_duration_ms: 40,
  p95_duration_ms: 90,
};

describe("dayMetricsToSeries", () => {
  it("maps day metrics and derives ok/failed plus cost per execution", () => {
    const [point] = dayMetricsToSeries([metric]);
    expect(point.day).toBe("10-01");
    expect(point.ok).toBe(8);
    expect(point.failed).toBe(2);
    expect(point.cost_per_execution).toBeCloseTo(0.05);
    expect(point.p95_duration_ms).toBe(300);
    expect(point.llm_calls).toBe(8);
  });

  it("guards the cost-per-execution division on empty days", () => {
    const [point] = dayMetricsToSeries([
      { ...metric, executions: 0, failed_executions: 0, total_cost: 0 },
    ]);
    expect(point.cost_per_execution).toBe(0);
    expect(point.ok).toBe(0);
  });

  it("tolerates a missing payload", () => {
    expect(dayMetricsToSeries(undefined)).toEqual([]);
  });
});

describe("failureRows", () => {
  it("pivots counts by day and kind, oldest day first", () => {
    expect(
      failureRows([
        { day: "2026-10-02", kind: "timeout", count: 1 },
        { day: "2026-10-01", kind: "timeout", count: 2 },
        { day: "2026-10-01", kind: "tool_error", count: 3 },
        { day: "2026-10-01", kind: "timeout", count: 1 },
      ])
    ).toEqual([
      { day: "10-01", timeout: 3, tool_error: 3 },
      { day: "10-02", timeout: 1 },
    ]);
  });
});

describe("entity rows", () => {
  it("labels a model with its provider and carries every chart field", () => {
    const [row] = modelRows([model]);
    expect(row.label).toBe("openai · gpt-4o-mini");
    expect(row.cost).toBe(0.002);
    expect(row.tokens).toBe(1000);
    expect(row.failed).toBe(1);
    expect(row.p95_duration_ms).toBe(300);
  });

  it("falls back to the key when a model row has no provider/model labels", () => {
    const [row] = modelRows([{ ...model, provider: null, model: null }]);
    expect(row.label).toBe("openai:gpt-4o-mini");
  });

  it("splits tool calls into ok and failed", () => {
    const [row] = toolRows([tool]);
    expect(row.label).toBe("search");
    expect(row.ok).toBe(4);
    expect(row.failed).toBe(1);
    expect(row.error_rate).toBe(0.2);
  });
});

describe("topBy", () => {
  it("sorts descending numerically and slices to the limit", () => {
    const rows = topBy(
      [
        { label: "a", cost: 1 },
        { label: "b", cost: 5 },
        { label: "c", cost: 3 },
      ],
      "cost",
      2
    );
    expect(rows.map((row) => row.label)).toEqual(["b", "c"]);
  });
});
