import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  useAlerts,
  useExecutions,
  useMetrics,
  useOverview,
  useWorkflows,
} from "../api/hooks";
import { useFilters } from "../state/FiltersContext";
import { PageHeader } from "../components/PageHeader";
import { FilterToolbar } from "../components/FilterToolbar";
import { RefreshButton } from "../components/RefreshButton";
import { TrendChart } from "../components/charts/TrendChart";
import { SeverityBadge, StatusBadge } from "../components/domain";
import {
  Alert,
  Button,
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
import { formatMs, formatPct, formatTokens } from "../lib/format";

export default function Client() {
  const { filters } = useFilters();
  const navigate = useNavigate();
  const overview = useOverview(filters);
  const metrics = useMetrics("total", filters);
  const workflows = useWorkflows(filters);
  const alerts = useAlerts();
  const [drilldown, setDrilldown] = useState<string | null>(null);

  const recent = useExecutions(filters, undefined, 20);
  const errors = useExecutions(
    { ...filters, workflow: drilldown ?? undefined },
    "error",
    200
  );

  const failuresByKind = useMemo(() => {
    const counts = new Map<string, number>();
    for (const execution of errors.data?.items ?? []) {
      const kind = execution.error_kind ?? "unclassified";
      counts.set(kind, (counts.get(kind) ?? 0) + 1);
    }
    return Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
  }, [errors.data]);

  const drilldownWorkflow = workflows.data?.items.find((w) => w.name === drilldown);
  const series = (metrics.data?.items ?? []).map((m) => ({
    day: m.day.slice(5),
    executions: m.executions,
    failed: m.failed_executions,
  }));

  const data = overview.data;
  const loadError = overview.error ?? metrics.error;

  return (
    <div className="page">
      <PageHeader
        title="Client"
        subTitle="Read-only usage view for the projects you belong to."
        extra={<RefreshButton />}
      />
      <FilterToolbar />

      <Alert
        variant="info"
        message="Scoped to your project memberships."
        detail="Cost and budget data are not exposed to client accounts; raw spans and prompts stay hidden."
      />

      {overview.isError ? <QueryError what="the client overview" error={loadError} /> : null}

      {overview.isLoading ? (
        <div className="grid grid-4">
          {Array.from({ length: 5 }, (_, i) => (
            <Skeleton key={i} shape="chart" />
          ))}
        </div>
      ) : (
        <div className="grid grid-4">
          <Metric label="Executions" value={data?.executions ?? 0} sub={`${data?.failed_executions ?? 0} failed`} />
          <Metric
            label="Error rate"
            value={formatPct(data?.error_rate)}
            tone={data && data.error_rate > 0 ? "danger" : "default"}
          />
          <Metric label="Avg duration" value={formatMs(data?.avg_duration_ms)} sub={`p50 ${formatMs(data?.p50_duration_ms)}`} />
          <Metric label="P95 latency" value={formatMs(data?.p95_duration_ms)} />
          <Metric label="Total tokens" value={formatTokens(data?.total_tokens)} />
        </div>
      )}

      <CardPanel title="Executions & errors" subTitle="Completed workflow roots per day">
        <div style={{ padding: "var(--global-dimension-size-100)" }}>
          {metrics.isLoading ? (
            <Skeleton shape="chart" />
          ) : series.length ? (
            <TrendChart
              data={series}
              series={[
                { key: "executions", label: "Executions", type: "bar", colorIndex: 6 },
                { key: "failed", label: "Failed", type: "line", colorIndex: 3 },
              ]}
              height={240}
            />
          ) : (
            <EmptyState title="No activity in range" description="Widen the filters or wait for the next ingest." />
          )}
        </div>
      </CardPanel>

      <div className="grid grid-2">
        <CardPanel title="Workflows" subTitle="Select a workflow to inspect failure kinds">
          {workflows.isLoading ? (
            <div className="stack" style={{ padding: 16 }}>
              <Skeleton width="80%" />
              <Skeleton width="60%" />
            </div>
          ) : workflows.data?.items.length ? (
            <TableWrap>
              <Table interactive>
                <thead>
                  <tr>
                    <Th>Workflow</Th>
                    <Th align="right">Executions</Th>
                    <Th align="right">Error rate</Th>
                    <Th align="right">Tokens</Th>
                  </tr>
                </thead>
                <tbody>
                  {workflows.data.items.map((workflow) => (
                    <Tr
                      key={workflow.name}
                      onClick={() => setDrilldown(workflow.name ?? null)}
                      data-selected={drilldown === workflow.name}
                    >
                      <Td className="table__cell--primary">{workflow.name ?? "unknown"}</Td>
                      <Td align="right" className="num">{workflow.executions}</Td>
                      <Td align="right" className="num">
                        <span className={workflow.error_rate ? "text-danger" : ""}>
                          {formatPct(workflow.error_rate)}
                        </span>
                      </Td>
                      <Td align="right" className="num">{formatTokens(workflow.total_tokens)}</Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
            </TableWrap>
          ) : (
            <EmptyState title="No workflows yet" description="Workflows appear once traces are ingested for your projects." />
          )}
        </CardPanel>

        <CardPanel
          title={drilldown ? `Failure kinds — ${drilldown}` : "Failure kinds"}
          subTitle={
            drilldown && drilldownWorkflow
              ? `${drilldownWorkflow.failed_executions ?? 0} of ${drilldownWorkflow.executions} executions failed`
              : "Pick a workflow on the left"
          }
          extra={
            drilldown ? (
              <Button variant="quiet" onClick={() => setDrilldown(null)}>
                Clear
              </Button>
            ) : undefined
          }
        >
          {!drilldown ? (
            <EmptyState
              title="No workflow selected"
              description="Failure classification is available per workflow — spans and prompts are never shown."
            />
          ) : errors.isLoading ? (
            <div className="stack" style={{ padding: 16 }}>
              <Skeleton width="70%" />
              <Skeleton width="50%" />
            </div>
          ) : failuresByKind.length ? (
            <TableWrap>
              <Table>
                <thead>
                  <tr>
                    <Th>Failure kind</Th>
                    <Th align="right">Count</Th>
                  </tr>
                </thead>
                <tbody>
                  {failuresByKind.map(([kind, count]) => (
                    <Tr key={kind}>
                      <Td className="table__cell--primary">{kind}</Td>
                      <Td align="right" className="num">{count}</Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
            </TableWrap>
          ) : (
            <EmptyState title="No classified failures" description="This workflow has no failing executions in range." />
          )}
        </CardPanel>
      </div>

      <CardPanel
        title="Recent executions"
        subTitle="Open an execution for its failure tree — no spans or prompts"
        extra={<Link to="/client">Back to top</Link>}
      >
        {recent.isLoading ? (
          <div className="stack" style={{ padding: 16 }}>
            <Skeleton width="80%" />
            <Skeleton width="60%" />
          </div>
        ) : recent.data?.items.length ? (
          <TableWrap>
            <Table interactive>
              <thead>
                <tr>
                  <Th>Time</Th>
                  <Th>Workflow</Th>
                  <Th>Status</Th>
                  <Th align="right">Duration</Th>
                  <Th align="right">Tokens</Th>
                  <Th>Failure</Th>
                </tr>
              </thead>
              <tbody>
                {recent.data.items.map((execution) => (
                  <Tr key={execution.id} onClick={() => navigate(`/engineering/${execution.id}`)}>
                    <Td className="muted num">
                      {execution.started_at ? new Date(execution.started_at).toLocaleString() : "—"}
                    </Td>
                    <Td>
                      <Link
                        to={`/engineering/${execution.id}`}
                        className="table__cell--primary truncate"
                      >
                        {execution.workflow ?? execution.trace_id}
                      </Link>
                    </Td>
                    <Td>
                      <StatusBadge status={execution.status} />
                    </Td>
                    <Td align="right" className="num">{formatMs(execution.duration_ms)}</Td>
                    <Td align="right" className="num">{formatTokens(execution.total_tokens)}</Td>
                    <Td className="muted">{execution.error_kind ?? "—"}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          </TableWrap>
        ) : (
          <TableEmpty colSpan={6}>No executions in range yet.</TableEmpty>
        )}
      </CardPanel>

      <CardPanel title="Open alerts" subTitle={alerts.data ? `${alerts.data.total} open` : undefined}>
        {alerts.isLoading ? (
          <div className="stack" style={{ padding: 16 }}>
            <Skeleton width="60%" />
            <Skeleton width="80%" />
          </div>
        ) : alerts.data?.items.length ? (
          alerts.data.items.map((alert) => (
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
          ))
        ) : (
          <EmptyState title="No open alerts" description="Nothing is crossing a configured threshold for your projects." />
        )}
      </CardPanel>
    </div>
  );
}
