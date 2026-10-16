import type { ReactNode } from "react";
import { CardPanel, EmptyState, Skeleton } from "../core";
import { TrendChart } from "./TrendChart";
import {
  formatMoney,
  formatMs,
  formatPct,
  formatTokens,
  formatUnitCost,
} from "../../lib/format";
import {
  failureRows,
  modelRows,
  toolRows,
  topBy,
  type FailureRow,
  type InsightPoint,
  type ModelRow,
  type ToolRow,
} from "../../lib/insightSeries";
import type { FailureSeriesItem, ModelInsight, ToolInsight } from "../../api/types";

/**
 * Shared insight panels (phoenix insights): one implementation of every chart
 * the Overview, Manager and Executive pages show, so the Phoenix-style panels
 * are composed rather than copy-pasted. Each panel is a fixed-height
 * `CardPanel` — nothing scrolls — with skeleton and empty states.
 */

const CHART_PADDING = { padding: "var(--global-dimension-size-100)" } as const;

function Panel({
  title,
  subTitle,
  loading,
  empty,
  emptyText,
  filters,
  children,
}: {
  title: string;
  subTitle?: string;
  loading?: boolean;
  empty: boolean;
  emptyText: string;
  filters?: ReactNode;
  children: ReactNode;
}) {
  return (
    <CardPanel title={title} subTitle={subTitle} extra={filters}>
      <div style={CHART_PADDING}>
        {loading ? (
          <Skeleton shape="chart" />
        ) : empty ? (
          <EmptyState title={emptyText} />
        ) : (
          children
        )}
      </div>
    </CardPanel>
  );
}

/* ---------------------------------------------------------------- time series */

export function CostChart({
  data,
  loading,
  height = 240,
  filters,
}: {
  data: InsightPoint[];
  loading?: boolean;
  height?: number;
  filters?: ReactNode;
}) {
  return (
    <Panel
      title="Cost over time"
      subTitle="USD per day"
      loading={loading}
      empty={!data.length}
      emptyText="No cost in range"
      filters={filters}
    >
      <TrendChart
        data={data}
        series={[{ key: "cost", label: "Cost", colorIndex: 0 }]}
        valueFormatter={formatMoney}
        height={height}
      />
    </Panel>
  );
}

export function CostPerExecutionChart({
  data,
  loading,
  height = 220,
  filters,
}: {
  data: InsightPoint[];
  loading?: boolean;
  height?: number;
  filters?: ReactNode;
}) {
  return (
    <Panel
      title="Cost per execution"
      subTitle="USD per execution, per day"
      loading={loading}
      empty={!data.length}
      emptyText="No executions in range"
      filters={filters}
    >
      <TrendChart
        data={data}
        series={[{ key: "cost_per_execution", label: "Cost / execution", colorIndex: 1 }]}
        valueFormatter={formatUnitCost}
        height={height}
      />
    </Panel>
  );
}

export function TrafficChart({
  data,
  loading,
  height = 240,
  filters,
}: {
  data: InsightPoint[];
  loading?: boolean;
  height?: number;
  filters?: ReactNode;
}) {
  return (
    <Panel
      title="Executions over time"
      subTitle="Succeeded vs failed per day"
      loading={loading}
      empty={!data.length}
      emptyText="No executions in range"
      filters={filters}
    >
      <TrendChart
        data={data}
        series={[
          { key: "ok", label: "Succeeded", type: "bar", stack: true, colorIndex: 6 },
          { key: "failed", label: "Failed", type: "bar", stack: true, colorIndex: 3 },
        ]}
        height={height}
      />
    </Panel>
  );
}

export function TokensChart({
  data,
  loading,
  height = 220,
  filters,
}: {
  data: InsightPoint[];
  loading?: boolean;
  height?: number;
  filters?: ReactNode;
}) {
  return (
    <Panel
      title="Tokens over time"
      subTitle="Input vs output tokens"
      loading={loading}
      empty={!data.length}
      emptyText="No token usage in range"
      filters={filters}
    >
      <TrendChart
        data={data}
        series={[
          { key: "input_tokens", label: "Input", colorIndex: 0, stack: true },
          { key: "output_tokens", label: "Output", colorIndex: 3, stack: true },
        ]}
        valueFormatter={formatTokens}
        height={height}
      />
    </Panel>
  );
}

export function LatencyChart({
  data,
  loading,
  height = 220,
  filters,
}: {
  data: InsightPoint[];
  loading?: boolean;
  height?: number;
  filters?: ReactNode;
}) {
  return (
    <Panel
      title="Latency over time"
      subTitle="p50 / p95 / p99 per day"
      loading={loading}
      empty={!data.length}
      emptyText="No latency in range"
      filters={filters}
    >
      <TrendChart
        data={data}
        series={[
          { key: "p50_duration_ms", label: "p50", colorIndex: 0 },
          { key: "p95_duration_ms", label: "p95", colorIndex: 3 },
          { key: "p99_duration_ms", label: "p99", colorIndex: 5, dashed: true },
        ]}
        valueFormatter={formatMs}
        height={height}
      />
    </Panel>
  );
}

export function ErrorRateChart({
  data,
  loading,
  height = 220,
  filters,
}: {
  data: InsightPoint[];
  loading?: boolean;
  height?: number;
  filters?: ReactNode;
}) {
  return (
    <Panel
      title="Error rate over time"
      subTitle="Failed executions per day"
      loading={loading}
      empty={!data.length}
      emptyText="No executions in range"
      filters={filters}
    >
      <TrendChart
        data={data}
        series={[{ key: "error_rate", label: "Error rate", colorIndex: 5 }]}
        valueFormatter={formatPct}
        height={height}
      />
    </Panel>
  );
}

export function CallsChart({
  data,
  loading,
  height = 220,
  filters,
}: {
  data: InsightPoint[];
  loading?: boolean;
  height?: number;
  filters?: ReactNode;
}) {
  return (
    <Panel
      title="LLM & tool calls"
      subTitle="Calls per day"
      loading={loading}
      empty={!data.length}
      emptyText="No calls in range"
      filters={filters}
    >
      <TrendChart
        data={data}
        series={[
          { key: "llm_calls", label: "LLM calls", colorIndex: 0 },
          { key: "tool_calls", label: "Tool calls", colorIndex: 4 },
        ]}
        height={height}
      />
    </Panel>
  );
}

export function FailuresByKindChart({
  items,
  kinds,
  loading,
  height = 220,
  filters,
}: {
  items: FailureSeriesItem[] | undefined;
  kinds: string[];
  loading?: boolean;
  height?: number;
  filters?: ReactNode;
}) {
  const rows: FailureRow[] = failureRows(items);
  return (
    <Panel
      title="Failures by kind"
      subTitle="Failing executions per day"
      loading={loading}
      empty={!rows.length}
      emptyText="No failures in range"
      filters={filters}
    >
      <TrendChart
        data={rows}
        series={kinds.map((kind, index) => ({
          key: kind,
          label: kind,
          type: "bar" as const,
          stack: true,
          colorIndex: index,
        }))}
        height={height}
      />
    </Panel>
  );
}

/* ------------------------------------------------------------- entity panels */

export function ModelsByCostChart({
  items,
  loading,
  limit = 8,
  height = 220,
  filters,
}: {
  items: ModelInsight[] | undefined;
  loading?: boolean;
  limit?: number;
  height?: number;
  filters?: ReactNode;
}) {
  const rows: ModelRow[] = topBy(modelRows(items), "cost", limit);
  return (
    <Panel
      title="Top models by cost"
      subTitle="Spend per provider · model"
      loading={loading}
      empty={!rows.length}
      emptyText="No model spend in range"
      filters={filters}
    >
      <TrendChart
        data={rows}
        xKey="label"
        series={[{ key: "cost", label: "Cost", type: "bar", colorIndex: 0 }]}
        valueFormatter={formatMoney}
        height={height}
      />
    </Panel>
  );
}

export function ModelsByTokensChart({
  items,
  loading,
  limit = 8,
  height = 220,
  filters,
}: {
  items: ModelInsight[] | undefined;
  loading?: boolean;
  limit?: number;
  height?: number;
  filters?: ReactNode;
}) {
  const rows: ModelRow[] = topBy(modelRows(items), "tokens", limit);
  return (
    <Panel
      title="Top models by tokens"
      subTitle="Input vs output tokens"
      loading={loading}
      empty={!rows.length}
      emptyText="No model tokens in range"
      filters={filters}
    >
      <TrendChart
        data={rows}
        xKey="label"
        series={[
          { key: "input_tokens", label: "Input", type: "bar", stack: true, colorIndex: 0 },
          { key: "output_tokens", label: "Output", type: "bar", stack: true, colorIndex: 3 },
        ]}
        valueFormatter={formatTokens}
        height={height}
      />
    </Panel>
  );
}

export function ModelLatencyChart({
  items,
  loading,
  limit = 8,
  height = 220,
  filters,
}: {
  items: ModelInsight[] | undefined;
  loading?: boolean;
  limit?: number;
  height?: number;
  filters?: ReactNode;
}) {
  const rows: ModelRow[] = topBy(modelRows(items), "p95_duration_ms", limit);
  return (
    <Panel
      title="Latency by model"
      subTitle="Average and p95 per provider · model"
      loading={loading}
      empty={!rows.length}
      emptyText="No model latency in range"
      filters={filters}
    >
      <TrendChart
        data={rows}
        xKey="label"
        series={[
          { key: "avg_duration_ms", label: "Average", type: "bar", colorIndex: 1 },
          { key: "p95_duration_ms", label: "p95", type: "bar", colorIndex: 3 },
        ]}
        valueFormatter={formatMs}
        height={height}
      />
    </Panel>
  );
}

export function ToolCallsChart({
  items,
  loading,
  limit = 8,
  height = 220,
  filters,
}: {
  items: ToolInsight[] | undefined;
  loading?: boolean;
  limit?: number;
  height?: number;
  filters?: ReactNode;
}) {
  const rows: ToolRow[] = topBy(toolRows(items), "calls", limit);
  return (
    <Panel
      title="Tool calls and errors"
      subTitle="Calls per tool, failed vs ok"
      loading={loading}
      empty={!rows.length}
      emptyText="No tool calls in range"
      filters={filters}
    >
      <TrendChart
        data={rows}
        xKey="label"
        series={[
          { key: "ok", label: "Succeeded", type: "bar", stack: true, colorIndex: 6 },
          { key: "failed", label: "Failed", type: "bar", stack: true, colorIndex: 3 },
        ]}
        height={height}
      />
    </Panel>
  );
}

export function ToolLatencyChart({
  items,
  loading,
  limit = 8,
  height = 220,
  filters,
}: {
  items: ToolInsight[] | undefined;
  loading?: boolean;
  limit?: number;
  height?: number;
  filters?: ReactNode;
}) {
  const rows: ToolRow[] = topBy(toolRows(items), "p95_duration_ms", limit);
  return (
    <Panel
      title="Slowest tools"
      subTitle="p95 duration per tool"
      loading={loading}
      empty={!rows.length}
      emptyText="No tool calls in range"
      filters={filters}
    >
      <TrendChart
        data={rows}
        xKey="label"
        series={[{ key: "p95_duration_ms", label: "p95", type: "bar", colorIndex: 5 }]}
        valueFormatter={formatMs}
        height={height}
      />
    </Panel>
  );
}
