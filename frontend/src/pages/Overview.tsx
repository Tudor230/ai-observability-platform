import { Link } from "react-router-dom";
import { useAlerts, useMetrics, useOverview } from "../api/hooks";
import { useFilters } from "../state/FiltersContext";
import { PageHeader } from "../components/PageHeader";
import { FilterToolbar } from "../components/FilterToolbar";
import { RefreshButton } from "../components/RefreshButton";
import { TrendChart } from "../components/charts/TrendChart";
import { SeverityBadge } from "../components/domain";
import {
  Alert,
  CardPanel,
  Delta,
  EmptyState,
  Metric,
  QueryError,
  Skeleton,
} from "../components/core";
import { formatMoney, formatMs, formatPct, formatTokens } from "../lib/format";

export default function Overview() {
  const { filters } = useFilters();
  const overview = useOverview(filters);
  const metrics = useMetrics("total", filters);
  const alerts = useAlerts();

  const data = overview.data;
  const series = (metrics.data?.items ?? []).map((m) => ({
    day: m.day.slice(5),
    cost: m.total_cost,
    executions: m.executions,
    input_tokens: m.input_tokens,
    output_tokens: m.output_tokens,
  }));

  const loadError = overview.error ?? metrics.error;
  const loading = overview.isLoading;

  return (
    <div className="page">
      <PageHeader
        title="Overview"
        subTitle="Usage, cost and reliability across every agent execution."
        extra={<RefreshButton />}
      />
      <FilterToolbar />

      {overview.isError ? (
        <QueryError what="the overview" error={loadError} />
      ) : null}

      {loading ? (
        <>
          <div className="grid grid-4">
            {Array.from({ length: 8 }, (_, i) => (
              <Skeleton key={i} shape="chart" />
            ))}
          </div>
          <Skeleton shape="chart" />
        </>
      ) : (
        <>
          <div className="grid grid-4">
            <Metric
              label="Total cost"
              value={formatMoney(data?.total_cost)}
              sub={<Delta pct={data?.deltas?.total_cost_pct} polarity="up-is-bad" />}
            />
            <Metric
              label="Executions"
              value={data?.executions ?? 0}
              sub={
                <>
                  <Delta pct={data?.deltas?.executions_pct} polarity="down-is-bad" />
                  <span className="muted">{data?.failed_executions ?? 0} failed</span>
                </>
              }
            />
            <Metric
              label="Error rate"
              value={formatPct(data?.error_rate)}
              tone={data && data.error_rate > 0 ? "danger" : "default"}
              sub={<Delta pct={data?.deltas?.error_rate_pct} polarity="up-is-bad" />}
            />
            <Metric label="Total tokens" value={formatTokens(data?.total_tokens)} />
            <Metric label="LLM calls" value={data?.llm_calls ?? 0} />
            <Metric label="Tool calls" value={data?.tool_calls ?? 0} />
            <Metric label="Avg duration" value={formatMs(data?.avg_duration_ms)} sub={`p50 ${formatMs(data?.p50_duration_ms)}`} />
            <Metric label="P95 latency" value={formatMs(data?.p95_duration_ms)} sub={`p99 ${formatMs(data?.p99_duration_ms)}`} />
            <Metric
              label="Open alerts"
              value={data?.open_alerts ?? 0}
              tone={data && data.open_alerts > 0 ? "warning" : "default"}
              sub={data && data.open_alerts > 0 ? <Link to="/manager">Review alerts</Link> : "All clear"}
            />
          </div>

          <div className="grid grid-2">
            <CardPanel title="Cost over time" subTitle="USD per day">
              <div style={{ padding: "var(--global-dimension-size-100)" }}>
                <TrendChart
                  data={series}
                  series={[{ key: "cost", label: "Cost", colorIndex: 0 }]}
                  valueFormatter={(v) => formatMoney(v)}
                  height={240}
                />
              </div>
            </CardPanel>
            <CardPanel title="Executions over time" subTitle="Completed workflow roots per day">
              <div style={{ padding: "var(--global-dimension-size-100)" }}>
                <TrendChart
                  data={series}
                  series={[{ key: "executions", label: "Executions", type: "bar", colorIndex: 6 }]}
                  height={240}
                />
              </div>
            </CardPanel>
          </div>

          <div className="grid grid-2">
            <CardPanel title="Tokens over time" subTitle="Input vs output tokens">
              <div style={{ padding: "var(--global-dimension-size-100)" }}>
                <TrendChart
                  data={series}
                  series={[
                    { key: "input_tokens", label: "Input", colorIndex: 0, stack: true },
                    { key: "output_tokens", label: "Output", colorIndex: 3, stack: true },
                  ]}
                  valueFormatter={(v) => formatTokens(v)}
                  height={220}
                />
              </div>
            </CardPanel>
            <CardPanel
              title="Open alerts"
              subTitle={alerts.data ? `${alerts.data.total} open` : undefined}
              extra={<Link to="/manager">View all</Link>}
            >
              {(alerts.data?.items ?? []).slice(0, 4).map((alert) => (
                <div className="list-row" key={alert.id}>
                  <SeverityBadge severity={alert.severity} />
                  <div className="list-row__main">
                    <span className="truncate">{alert.message}</span>
                    <span className="muted" style={{ fontSize: 12 }}>
                      {alert.dimension}
                      {alert.dimension_key ? ` · ${alert.dimension_key}` : ""}
                    </span>
                  </div>
                  <span className="spacer" />
                  <span className="muted" style={{ fontSize: 12 }}>
                    {alert.triggered_at ? new Date(alert.triggered_at).toLocaleString() : ""}
                  </span>
                </div>
              ))}
              {alerts.isError ? (
                <div style={{ padding: 16 }}>
                  <QueryError what="alerts" error={alerts.error} />
                </div>
              ) : null}
              {!alerts.isError && !alerts.isLoading && !alerts.data?.items?.length ? (
                <EmptyState
                  title="No open alerts"
                  description="Budgets are tracking within thresholds for the selected range."
                />
              ) : null}
              {alerts.isLoading ? (
                <div className="stack" style={{ padding: 16 }}>
                  <Skeleton width="60%" />
                  <Skeleton width="80%" />
                  <Skeleton width="40%" />
                </div>
              ) : null}
            </CardPanel>
          </div>

          {metrics.isError ? <QueryError what="time series metrics" error={metrics.error} /> : null}
        </>
      )}

      {overview.isLoading ? null : (
        <Alert
          variant="info"
          message="All values are computed by the backend from ingested OTLP traces."
          detail="Unpriced models appear without a cost until a matching price is configured."
        />
      )}
    </div>
  );
}
