import { useMemo } from "react";
import { Link } from "react-router-dom";
import {
  useAlerts,
  useFailuresSeries,
  useMetrics,
  useOverview,
} from "../api/hooks";
import { useAuth } from "../state/AuthContext";
import { useFilters } from "../state/FiltersContext";
import { PageHeader } from "../components/PageHeader";
import { FilterChips, FiltersControl } from "../components/FiltersControl";
import { RefreshButton } from "../components/RefreshButton";
import { TrendChart } from "../components/charts/TrendChart";
import { SeverityBadge } from "../components/domain";
import {
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
  const { costVisible, hasRole } = useAuth();
  const overview = useOverview(filters);
  const metrics = useMetrics("total", filters);
  const alerts = useAlerts();
  const canSeeFailures = hasRole("engineer", "manager", "client");
  const failures = useFailuresSeries(filters, canSeeFailures);

  const data = overview.data;
  const series = (metrics.data?.items ?? []).map((m) => ({
    day: m.day.slice(5),
    cost: m.total_cost,
    executions: m.executions,
    ok: Math.max(0, m.executions - m.failed_executions),
    failed: m.failed_executions,
    input_tokens: m.input_tokens,
    output_tokens: m.output_tokens,
    p50_duration_ms: m.p50_duration_ms,
    p95_duration_ms: m.p95_duration_ms,
    p99_duration_ms: m.p99_duration_ms,
    error_rate: m.error_rate,
  }));

  const failureKinds = failures.data?.kinds ?? [];
  const failureRows = useMemo(() => {
    const byDay = new Map<string, Record<string, number>>();
    for (const item of failures.data?.items ?? []) {
      const row = byDay.get(item.day) ?? {};
      row[item.kind] = (row[item.kind] ?? 0) + item.count;
      byDay.set(item.day, row);
    }
    return Array.from(byDay.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([day, counts]) => ({ day: day.slice(5), ...counts }));
  }, [failures.data]);

  const loadError = overview.error ?? metrics.error;
  const loading = overview.isLoading;

  return (
    <div className="page">
      <PageHeader
        title="Overview"
        subTitle="Usage, cost and reliability across every agent execution."
        extra={
          <>
            <FiltersControl dimensions={["days", "project"]} />
            <RefreshButton />
          </>
        }
      />
      <FilterChips dimensions={["days", "project"]} />

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
            {costVisible ? (
              <Metric
                label="Total cost"
                value={formatMoney(data?.total_cost)}
                sub={<Delta pct={data?.deltas?.total_cost_pct} polarity="up-is-bad" />}
              />
            ) : null}
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
              sub={data && data.open_alerts > 0 ? <Link to="/alerts">Review alerts</Link> : "All clear"}
            />
          </div>

          <div className="grid grid-2">
            {costVisible ? (
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
            ) : null}
            <CardPanel title="Executions over time" subTitle="Succeeded vs failed per day">
              <div style={{ padding: "var(--global-dimension-size-100)" }}>
                <TrendChart
                  data={series}
                  series={[
                    { key: "ok", label: "Succeeded", type: "bar", stack: true, colorIndex: 6 },
                    { key: "failed", label: "Failed", type: "bar", stack: true, colorIndex: 3 },
                  ]}
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
            <CardPanel title="Latency over time" subTitle="p50 / p95 / p99 per day">
              <div style={{ padding: "var(--global-dimension-size-100)" }}>
                <TrendChart
                  data={series}
                  series={[
                    { key: "p50_duration_ms", label: "p50", colorIndex: 0 },
                    { key: "p95_duration_ms", label: "p95", colorIndex: 3 },
                    { key: "p99_duration_ms", label: "p99", colorIndex: 5, dashed: true },
                  ]}
                  valueFormatter={(v) => formatMs(v)}
                  height={220}
                />
              </div>
            </CardPanel>
          </div>

          {canSeeFailures ? (
            <CardPanel title="Failures by kind" subTitle="Failing executions per day">
              <div style={{ padding: "var(--global-dimension-size-100)" }}>
                {failures.isLoading ? (
                  <Skeleton shape="chart" />
                ) : failureRows.length ? (
                  <TrendChart
                    data={failureRows}
                    series={failureKinds.map((kind, index) => ({
                      key: kind,
                      label: kind,
                      type: "bar" as const,
                      stack: true,
                      colorIndex: index,
                    }))}
                    height={220}
                  />
                ) : (
                  <EmptyState
                    title="No failures in range"
                    description="Every captured execution completed without a classified failure."
                  />
                )}
              </div>
            </CardPanel>
          ) : null}

          <div className="grid grid-2">
            <CardPanel title="Error rate over time" subTitle="Failed executions per day">
              <div style={{ padding: "var(--global-dimension-size-100)" }}>
                <TrendChart
                  data={series}
                  series={[{ key: "error_rate", label: "Error rate", colorIndex: 5 }]}
                  valueFormatter={(v) => formatPct(v)}
                  height={200}
                />
              </div>
            </CardPanel>
            <CardPanel
              title="Open alerts"
              subTitle={alerts.data ? `${alerts.data.total} open` : undefined}
              extra={<Link to="/alerts">View all</Link>}
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
    </div>
  );
}
