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
import {
  CostChart,
  ErrorRateChart,
  FailuresByKindChart,
  LatencyChart,
  TokensChart,
  TrafficChart,
} from "../components/charts/insights";
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
import { dayMetricsToSeries } from "../lib/insightSeries";

export default function Overview() {
  const { filters } = useFilters();
  const { costVisible, hasRole } = useAuth();
  const overview = useOverview(filters);
  const metrics = useMetrics("total", filters);
  const alerts = useAlerts();
  const canSeeFailures = hasRole("engineer", "manager", "client");
  const failures = useFailuresSeries(filters, canSeeFailures);

  const data = overview.data;
  const points = useMemo(
    () => dayMetricsToSeries(metrics.data?.items),
    [metrics.data]
  );
  const failureKinds = failures.data?.kinds ?? [];

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
              <CostChart data={points} loading={metrics.isLoading} />
            ) : null}
            <TrafficChart data={points} loading={metrics.isLoading} />
          </div>

          <div className="grid grid-2">
            <TokensChart data={points} loading={metrics.isLoading} />
            <LatencyChart data={points} loading={metrics.isLoading} />
          </div>

          {canSeeFailures ? (
            <FailuresByKindChart
              items={failures.data?.items}
              kinds={failureKinds}
              loading={failures.isLoading}
            />
          ) : null}

          <div className="grid grid-2">
            <ErrorRateChart data={points} loading={metrics.isLoading} height={200} />
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
