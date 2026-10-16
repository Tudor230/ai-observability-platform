import { useMemo } from "react";
import {
  useCosts,
  useFailuresSeries,
  useMetrics,
  useModels,
  useOverview,
  useProjectNameMap,
} from "../api/hooks";
import { useFilters } from "../state/FiltersContext";
import { PageHeader } from "../components/PageHeader";
import { FilterChips, FiltersControl } from "../components/FiltersControl";
import { RefreshButton } from "../components/RefreshButton";
import { TrendChart } from "../components/charts/TrendChart";
import {
  CostChart,
  CostPerExecutionChart,
  ErrorRateChart,
  FailuresByKindChart,
  LatencyChart,
  ModelLatencyChart,
  ModelsByCostChart,
  ModelsByTokensChart,
  TokensChart,
  TrafficChart,
} from "../components/charts/insights";
import { CostCard, CostCardBars } from "../components/CostCard";
import { TableFilterChips, TableFilters } from "../components/TableFilters";
import { useTableFilters } from "../state/useTableFilters";
import {
  CardPanel,
  Delta,
  EmptyState,
  Metric,
  QueryError,
  Skeleton,
} from "../components/core";
import { formatMoney, formatMs, formatPct, formatTokens, formatUnitCost } from "../lib/format";
import { buildForecast, forecastAsOf } from "../lib/forecast";
import { dayMetricsToSeries } from "../lib/insightSeries";
import type { DayMetric } from "../api/types";

const FORECAST_DAYS = 7;

function buildChartData(items: DayMetric[], forecast: { day: string; cost: number }[]) {
  const history: { day: string; cost?: number; forecast?: number }[] = items.map((m) => ({
    day: m.day.slice(5),
    cost: m.total_cost,
  }));
  if (forecast.length && history.length) {
    history[history.length - 1].forecast = history[history.length - 1].cost;
  }
  for (const point of forecast) {
    history.push({ day: point.day.slice(5), forecast: point.cost });
  }
  return history;
}

export default function Executive() {
  const { filters } = useFilters();
  const overview = useOverview(filters);
  // Each card filters independently (namespaced URL state, refinements v3).
  const projectCard = useTableFilters("projects");
  const modelCard = useTableFilters("models");
  const byModel = useCosts("model", { ...filters, ...modelCard.filters });
  const byProject = useCosts("project", { ...filters, ...projectCard.filters });
  const projectNames = useProjectNameMap();
  const trends = useMetrics("total", filters);
  // Model economics share the Models card's filter; the time-series panels
  // follow the page window like Overview.
  const models = useModels({ ...filters, ...modelCard.filters });
  const failures = useFailuresSeries(filters, true);

  const data = overview.data;
  const items = trends.data?.items ?? [];
  const series = items.map((m) => ({ day: m.day, cost: m.total_cost ?? 0 }));
  const forecast = buildForecast(series, FORECAST_DAYS, forecastAsOf());
  const forecastTotal = forecast.reduce((sum, p) => sum + p.cost, 0);

  const executions = data?.executions ?? 0;
  const failed = data?.failed_executions ?? 0;
  const totalCost = data?.total_cost ?? 0;
  const costPerExecution = executions ? totalCost / executions : null;
  const tokens = data?.total_tokens ?? 0;
  const costPer1mTokens = tokens ? (totalCost / tokens) * 1_000_000 : null;
  const points = useMemo(() => dayMetricsToSeries(trends.data?.items), [trends.data]);
  const inputTokens = items.reduce((sum, m) => sum + (m.input_tokens ?? 0), 0);
  const outputTokens = items.reduce((sum, m) => sum + (m.output_tokens ?? 0), 0);
  const deltas = data?.deltas;

  const anyError =
    overview.isError || byModel.isError || byProject.isError || models.isError;
  const loadError = overview.error ?? byModel.error ?? byProject.error ?? models.error;

  return (
    <div className="page">
      <PageHeader
        title="Executive"
        subTitle="Unit economics of agentic AI — total spend, cost per execution and forecast."
        extra={
          <>
            <FiltersControl dimensions={["days"]} />
            <RefreshButton />
          </>
        }
      />
      <FilterChips dimensions={["days"]} />

      {anyError ? <QueryError what="executive data" error={loadError} /> : null}

      {overview.isLoading ? (
        <div className="grid grid-3">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} shape="chart" />
          ))}
        </div>
      ) : (
        <div className="grid grid-3">
          <Metric
            label="Total AI cost"
            value={formatMoney(totalCost)}
            sub={<Delta pct={deltas?.total_cost_pct} polarity="up-is-bad" />}
          />
          <Metric label="Cost per 1M tokens" value={formatUnitCost(costPer1mTokens)} />
          <Metric label="Cost per execution" value={formatUnitCost(costPerExecution)} />
          <Metric
            label="Executions"
            value={executions}
            sub={
              <>
                {failed} failed <Delta pct={deltas?.executions_pct} polarity="down-is-bad" />
              </>
            }
          />
          <Metric
            label="Total tokens"
            value={formatTokens(tokens)}
            sub={`${formatTokens(inputTokens)} in / ${formatTokens(outputTokens)} out`}
          />
          <Metric
            label="p95 latency"
            value={formatMs(data?.p95_duration_ms)}
            sub={`p50 ${formatMs(data?.p50_duration_ms)}`}
          />
        </div>
      )}

      <div className="grid grid-3">
        <TrafficChart data={points} loading={trends.isLoading} />
        <LatencyChart data={points} loading={trends.isLoading} />
        <ErrorRateChart data={points} loading={trends.isLoading} />
      </div>

      <div className="grid grid-3">
        <TokensChart data={points} loading={trends.isLoading} />
        <CostPerExecutionChart data={points} loading={trends.isLoading} />
        <FailuresByKindChart
          items={failures.data?.items}
          kinds={failures.data?.kinds ?? []}
          loading={failures.isLoading}
        />
      </div>

      <div className="grid grid-3">
        <ModelsByCostChart items={models.data?.items} loading={models.isLoading} />
        <ModelsByTokensChart items={models.data?.items} loading={models.isLoading} />
        <ModelLatencyChart items={models.data?.items} loading={models.isLoading} />
      </div>

      <CardPanel
        title="Forecast"
        subTitle={`Linear projection over the next ${FORECAST_DAYS} days — estimate`}
        extra={
          forecast.length ? (
            <span className="muted">
              Projected: <strong>{formatMoney(forecastTotal)}</strong>
            </span>
          ) : undefined
        }
      >
        {trends.isLoading ? (
          <div style={{ padding: 16 }}>
            <Skeleton shape="chart" />
          </div>
        ) : forecast.length ? (
          <div style={{ padding: "var(--global-dimension-size-100)" }}>
            <TrendChart
              data={buildChartData(items, forecast)}
              series={[
                { key: "cost", label: "Actual cost", type: "line", colorIndex: 0 },
                { key: "forecast", label: "Forecast", type: "line", colorIndex: 3, dashed: true },
              ]}
              valueFormatter={(v) => formatMoney(v)}
              height={260}
            />
          </div>
        ) : (
          <EmptyState
            title="Not enough cost history to forecast"
            description={`At least 3 days with cost are required — currently ${series.filter((p) => (p.cost ?? 0) > 0).length}.`}
          />
        )}
      </CardPanel>

      <div className="grid grid-2">
        <CostCard
          filters={<TableFilters card="projects" title="Projects" />}
          filterChips={<TableFilterChips card="projects" />}
          title="Projects"
          subTitle="Cost, reliability and volume per project"
          loading={byProject.isLoading}
          emptyBreakdown="No project spend in range"
          emptyDetail="No project spend in range."
          columns={["Project", "Executions", "Error rate", "Tokens", "Cost"]}
          rows={(byProject.data?.items ?? []).map((item) => {
            const key = item.key ?? String(item.name);
            const label = projectNames.get(item.key ?? "") ?? item.key ?? "—";
            return {
              key,
              bar: {
                label,
                value: item.total_cost ?? 0,
                valueLabel: formatMoney(item.total_cost),
                sublabel: `${item.executions} executions`,
              },
              cells: [
                label,
                item.executions,
                <span className={item.error_rate ? "text-danger" : ""}>
                  {formatPct(item.error_rate)}
                </span>,
                formatTokens(item.total_tokens),
                formatMoney(item.total_cost),
              ],
              sortValues: [
                label,
                item.executions,
                item.error_rate ?? 0,
                item.total_tokens,
                item.total_cost ?? 0,
              ],
            };
          })}
          breakdown={(visible) => <CostCardBars rows={visible} />}
        />

        <CostCard
          filters={<TableFilters card="models" title="Models" />}
          filterChips={<TableFilterChips card="models" />}
          title="Models"
          subTitle="Provider · model spend"
          loading={byModel.isLoading}
          emptyBreakdown="No model usage in range"
          emptyDetail="No model usage in range."
          columns={["Provider · model", "Cost", "Input tokens", "Output tokens"]}
          rows={(byModel.data?.items ?? []).map((m) => {
            const key = m.key ?? `${m.provider}-${m.model}`;
            const label = [m.provider, m.model].filter(Boolean).join(" · ") || "unknown";
            return {
              key,
              bar: {
                label,
                value: m.total_cost ?? 0,
                valueLabel: formatMoney(m.total_cost),
                sublabel: `${m.executions} executions`,
              },
              cells: [
                label,
                formatMoney(m.total_cost),
                formatTokens(m.input_tokens),
                formatTokens(m.output_tokens),
              ],
              sortValues: [
                label,
                m.total_cost ?? 0,
                m.input_tokens ?? 0,
                m.output_tokens ?? 0,
              ],
            };
          })}
          breakdown={(visible) => <CostCardBars rows={visible} />}
        />
      </div>

      <CostChart data={points} loading={trends.isLoading} />
    </div>
  );
}
