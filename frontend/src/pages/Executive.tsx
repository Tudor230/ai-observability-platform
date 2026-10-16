import { useCosts, useMetrics, useOverview, useProjectNameMap } from "../api/hooks";
import { useFilters } from "../state/FiltersContext";
import { PageHeader } from "../components/PageHeader";
import { FilterChips, FiltersControl } from "../components/FiltersControl";
import { RefreshButton } from "../components/RefreshButton";
import { TrendChart } from "../components/charts/TrendChart";
import { CostCard, CostCardBars } from "../components/CostCard";
import { TableFilterChips, TableFilters } from "../components/TableFilters";
import { useTableFilters } from "../state/useTableFilters";
import {
  CardPanel,
  EmptyState,
  Metric,
  QueryError,
  Skeleton,
} from "../components/core";
import { formatMoney, formatPct, formatTokens } from "../lib/format";
import { buildForecast, forecastAsOf } from "../lib/forecast";
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

  const data = overview.data;
  const items = trends.data?.items ?? [];
  const series = items.map((m) => ({ day: m.day, cost: m.total_cost ?? 0 }));
  const forecast = buildForecast(series, FORECAST_DAYS, forecastAsOf());
  const forecastTotal = forecast.reduce((sum, p) => sum + p.cost, 0);

  const executions = data?.executions ?? 0;
  const failed = data?.failed_executions ?? 0;
  const successful = Math.max(0, executions - failed);
  const totalCost = data?.total_cost ?? 0;
  const costPerExecution = executions ? totalCost / executions : null;
  const costPerSuccess = successful ? totalCost / successful : null;
  const tokens = data?.total_tokens ?? 0;
  const costPer1kTokens = tokens ? (totalCost / tokens) * 1000 : null;

  const anyError = overview.isError || byModel.isError || byProject.isError;
  const loadError = overview.error ?? byModel.error ?? byProject.error;

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
        <div className="grid grid-4">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} shape="chart" />
          ))}
        </div>
      ) : (
        <div className="grid grid-4">
          <Metric label="Total AI cost" value={formatMoney(totalCost)} />
          <Metric label="Cost per execution" value={formatMoney(costPerExecution)} />
          <Metric label="Cost per successful execution" value={formatMoney(costPerSuccess)} />
          <Metric
            label="Cost per 1k tokens"
            value={costPer1kTokens === null ? "—" : formatMoney(costPer1kTokens)}
          />
          <Metric label="Total tokens" value={formatTokens(tokens)} />
          <Metric
            label="Successful executions"
            value={successful}
            sub={`${failed} failed`}
          />
        </div>
      )}

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

      <CardPanel title="Cost trend" subTitle="USD per day">
        <div style={{ padding: "var(--global-dimension-size-100)" }}>
          <TrendChart
            data={items.map((m) => ({ day: m.day.slice(5), cost: m.total_cost }))}
            series={[{ key: "cost", label: "Cost", colorIndex: 0 }]}
            valueFormatter={(v) => formatMoney(v)}
            height={240}
          />
        </div>
      </CardPanel>
    </div>
  );
}
