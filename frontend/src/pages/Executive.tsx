import { useCosts, useMetrics, useOverview } from "../api/hooks";
import { useFilters } from "../state/FiltersContext";
import { PageHeader } from "../components/PageHeader";
import { FilterToolbar } from "../components/FilterToolbar";
import { RefreshButton } from "../components/RefreshButton";
import { TrendChart } from "../components/charts/TrendChart";
import {
  CardPanel,
  EmptyState,
  Metric,
  QueryError,
  Skeleton,
  Table,
  TableEmpty,
  TableWrap,
  Td,
  Th,
  Tr,
} from "../components/core";
import { formatMoney, formatTokens } from "../lib/format";
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
  const byClient = useCosts("client", filters);
  const byModel = useCosts("model", filters);
  const trends = useMetrics("total", filters);

  const data = overview.data;
  const items = trends.data?.items ?? [];
  const series = items.map((m) => ({ day: m.day, cost: m.total_cost }));
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

  const anyError = overview.isError || byClient.isError || byModel.isError;
  const loadError = overview.error ?? byClient.error ?? byModel.error;

  return (
    <div className="page">
      <PageHeader
        title="Executive"
        subTitle="Unit economics of agentic AI — total spend, cost per execution and forecast."
        extra={<RefreshButton />}
      />
      <FilterToolbar />

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
            description={`At least 3 days with cost are required — currently ${series.filter((p) => p.cost > 0).length}.`}
          />
        )}
      </CardPanel>

      <div className="grid grid-2">
        <CardPanel title="Cost per client (service)" subTitle="Spend and volume by client">
          <TableWrap>
            <Table>
              <thead>
                <tr>
                  <Th>Client</Th>
                  <Th align="right">Cost</Th>
                  <Th align="right">Executions</Th>
                  <Th align="right">LLM calls</Th>
                </tr>
              </thead>
              {byClient.data?.items?.length ? (
                <tbody>
                  {byClient.data.items.map((c) => (
                    <Tr key={c.key}>
                      <Td className="table__cell--primary">{c.key}</Td>
                      <Td align="right" className="num">
                        {formatMoney(c.total_cost)}
                      </Td>
                      <Td align="right" className="num">
                        {c.executions}
                      </Td>
                      <Td align="right" className="num">
                        {c.llm_calls ?? 0}
                      </Td>
                    </Tr>
                  ))}
                </tbody>
              ) : (
                <TableEmpty colSpan={4}>No client spend in range.</TableEmpty>
              )}
            </Table>
          </TableWrap>
        </CardPanel>

        <CardPanel title="Cost by model" subTitle="Provider and model consumption">
          <TableWrap>
            <Table>
              <thead>
                <tr>
                  <Th>Provider · model</Th>
                  <Th align="right">Cost</Th>
                  <Th align="right">Input tokens</Th>
                  <Th align="right">Output tokens</Th>
                </tr>
              </thead>
              {byModel.data?.items?.length ? (
                <tbody>
                  {byModel.data.items.map((m) => (
                    <Tr key={m.key}>
                      <Td className="table__cell--primary">
                        {m.provider ? `${m.provider} · ` : ""}
                        {m.model}
                      </Td>
                      <Td align="right" className="num">
                        {formatMoney(m.total_cost)}
                      </Td>
                      <Td align="right" className="num">
                        {formatTokens(m.input_tokens)}
                      </Td>
                      <Td align="right" className="num">
                        {formatTokens(m.output_tokens)}
                      </Td>
                    </Tr>
                  ))}
                </tbody>
              ) : (
                <TableEmpty colSpan={4}>No model usage in range.</TableEmpty>
              )}
            </Table>
          </TableWrap>
        </CardPanel>
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
