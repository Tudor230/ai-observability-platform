import { useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  useAgents,
  useAlerts,
  useBudgetStatus,
  useClients,
  useCosts,
  useMetrics,
  useOverview,
  useWorkflows,
} from "../api/hooks";
import { api } from "../api/client";
import type { BudgetStatus } from "../api/types";
import { useAuth } from "../state/AuthContext";
import { useFilters } from "../state/FiltersContext";
import { PageHeader } from "../components/PageHeader";
import { FilterToolbar } from "../components/FilterToolbar";
import { RefreshButton } from "../components/RefreshButton";
import { BudgetDialog } from "../components/BudgetDialog";
import { TrendChart } from "../components/charts/TrendChart";
import { BreakdownBars } from "../components/charts/BreakdownBars";
import { SeverityBadge } from "../components/domain";
import {
  Button,
  CardPanel,
  Dialog,
  EmptyState,
  Metric,
  Progress,
  QueryError,
  Skeleton,
  Table,
  TableEmpty,
  TableWrap,
  Td,
  Th,
  Tr,
  useToast,
} from "../components/core";
import { formatMoney, formatPct, formatTokens } from "../lib/format";

export default function Manager() {
  const { filters } = useFilters();
  const { hasRole } = useAuth();
  const queryClient = useQueryClient();
  const overview = useOverview(filters);
  const costsByWorkflow = useCosts("workflow", filters);
  const costsByClient = useCosts("client", filters);
  const costsByTeam = useCosts("team", filters);
  const workflows = useWorkflows(filters);
  const clients = useClients(filters);
  const agents = useAgents(filters);
  const alerts = useAlerts();
  const trends = useMetrics("total", filters);
  const budgets = useBudgetStatus();

  const canCreateGlobal = hasRole("exec");
  const toast = useToast();
  const [budgetDialog, setBudgetDialog] = useState<{
    open: boolean;
    budget: BudgetStatus | null;
  }>({ open: false, budget: null });
  const [deletingBudget, setDeletingBudget] = useState<BudgetStatus | null>(null);
  const [budgetBusy, setBudgetBusy] = useState(false);
  const [budgetError, setBudgetError] = useState<string | null>(null);

  const refreshBudgets = () => {
    void queryClient.invalidateQueries({ queryKey: ["budgets"] });
  };

  const removeBudget = async () => {
    if (!deletingBudget) return;
    setBudgetBusy(true);
    setBudgetError(null);
    try {
      await api.budgets.remove(deletingBudget.id);
      toast.success("Budget deleted.");
      setDeletingBudget(null);
      refreshBudgets();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to delete the budget.";
      setBudgetError(message);
      toast.error(message);
    } finally {
      setBudgetBusy(false);
    }
  };

  const loadError =
    overview.error ?? costsByWorkflow.error ?? costsByClient.error ?? workflows.error;
  const anyError =
    overview.isError ||
    costsByWorkflow.isError ||
    costsByClient.isError ||
    workflows.isError ||
    alerts.isError ||
    budgets.isError;

  const trendSeries = (trends.data?.items ?? []).map((m) => ({
    day: m.day.slice(5),
    total_cost: m.total_cost,
    executions: m.executions,
    tool_calls: m.tool_calls,
  }));

  return (
    <div className="page">
      <PageHeader
        title="Manager"
        subTitle="Spend by workflow and client, budget health and agent efficiency."
        extra={<RefreshButton />}
      />
      <FilterToolbar />

      {anyError ? <QueryError what="manager data" error={loadError} /> : null}

      {overview.isLoading ? (
        <div className="grid grid-4">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} shape="chart" />
          ))}
        </div>
      ) : (
        <div className="grid grid-4">
          <Metric label="Total cost" value={formatMoney(overview.data?.total_cost)} />
          <Metric label="Executions" value={overview.data?.executions ?? 0} />
          <Metric
            label="Error rate"
            value={formatPct(overview.data?.error_rate)}
            tone={overview.data?.error_rate ? "danger" : "default"}
          />
          <Metric
            label="Open alerts"
            value={alerts.data?.total ?? 0}
            tone={alerts.data?.total ? "warning" : "default"}
          />
        </div>
      )}

      <div className="grid grid-2">
        <CardPanel title="Cost by workflow" subTitle="USD in range">
          {(costsByWorkflow.data?.items ?? []).length ? (
            <BreakdownBars
              rows={(costsByWorkflow.data?.items ?? []).map((item) => ({
                key: item.key ?? String(item.name),
                label: item.key ?? item.name ?? "—",
                value: item.total_cost ?? 0,
                valueLabel: formatMoney(item.total_cost),
                sublabel: [
                  `${item.executions} executions`,
                  item.error_rate !== undefined && item.error_rate !== null
                    ? `${formatPct(item.error_rate)} errors`
                    : null,
                ]
                  .filter(Boolean)
                  .join(" · "),
                href: `/engineering?workflow=${encodeURIComponent(item.key ?? item.name ?? "")}`,
              }))}
            />
          ) : costsByWorkflow.isLoading ? (
            <div className="stack" style={{ padding: 16 }}>
              <Skeleton width="80%" />
              <Skeleton width="60%" />
              <Skeleton width="70%" />
            </div>
          ) : (
            <EmptyState title="No workflow cost yet" description="Costs appear once executions are priced." />
          )}
        </CardPanel>

        <CardPanel title="Cost by client" subTitle="USD in range">
          {(costsByClient.data?.items ?? []).length ? (
            <BreakdownBars
              rows={(costsByClient.data?.items ?? []).map((item) => ({
                key: item.key ?? String(item.name),
                label: item.key ?? item.name ?? "—",
                value: item.total_cost ?? 0,
                valueLabel: formatMoney(item.total_cost),
                sublabel: `${item.executions} executions · ${formatTokens(item.total_tokens)} tokens`,
                href: `/engineering?client_id=${encodeURIComponent(item.key ?? item.name ?? "")}`,
              }))}
            />
          ) : costsByClient.isLoading ? (
            <div className="stack" style={{ padding: 16 }}>
              <Skeleton width="80%" />
              <Skeleton width="60%" />
              <Skeleton width="70%" />
            </div>
          ) : (
            <EmptyState title="No client cost yet" description="Costs appear once executions are priced." />
          )}
        </CardPanel>
      </div>

      <div className="grid grid-2">
        <CardPanel title="Workflows" subTitle="Reliability and cost per workflow">
          <TableWrap>
            <Table>
              <thead>
                <tr>
                  <Th>Workflow</Th>
                  <Th align="right">Executions</Th>
                  <Th align="right">Error rate</Th>
                  <Th align="right">Cost</Th>
                </tr>
              </thead>
              {workflows.data?.items?.length ? (
                <tbody>
                  {workflows.data.items.map((w) => (
                    <Tr key={w.name}>
                      <Td className="table__cell--primary">{w.name}</Td>
                      <Td align="right" className="num">
                        {w.executions}
                      </Td>
                      <Td align="right" className="num">
                        <span className={w.error_rate ? "text-danger" : ""}>{formatPct(w.error_rate)}</span>
                      </Td>
                      <Td align="right" className="num">
                        {formatMoney(w.total_cost)}
                      </Td>
                    </Tr>
                  ))}
                </tbody>
              ) : (
                <TableEmpty colSpan={4}>No workflows in range.</TableEmpty>
              )}
            </Table>
          </TableWrap>
        </CardPanel>

        <CardPanel title="Clients" subTitle="Consumption and cost per client">
          <TableWrap>
            <Table>
              <thead>
                <tr>
                  <Th>Client</Th>
                  <Th align="right">Executions</Th>
                  <Th align="right">Tokens</Th>
                  <Th align="right">Cost</Th>
                </tr>
              </thead>
              {clients.data?.items?.length ? (
                <tbody>
                  {clients.data.items.map((c) => (
                    <Tr key={c.client_id}>
                      <Td className="table__cell--primary">{c.client_id}</Td>
                      <Td align="right" className="num">
                        {c.executions}
                      </Td>
                      <Td align="right" className="num">
                        {formatTokens(c.total_tokens)}
                      </Td>
                      <Td align="right" className="num">
                        {formatMoney(c.total_cost)}
                      </Td>
                    </Tr>
                  ))}
                </tbody>
              ) : (
                <TableEmpty colSpan={4}>No clients in range.</TableEmpty>
              )}
            </Table>
          </TableWrap>
        </CardPanel>
      </div>

      <CardPanel title="Cost by team" subTitle="Spend per team in your scope">
        {(costsByTeam.data?.items ?? []).length ? (
          <div style={{ padding: "var(--global-dimension-size-100)" }}>
            <BreakdownBars
              rows={(costsByTeam.data?.items ?? []).map((item) => ({
                key: item.key ?? String(item.name),
                label: item.key ?? item.name ?? "unassigned",
                value: item.total_cost ?? 0,
                valueLabel: formatMoney(item.total_cost),
                sublabel: `${item.executions} executions`,
              }))}
            />
          </div>
        ) : costsByTeam.isLoading ? (
          <div className="stack" style={{ padding: 16 }}>
            <Skeleton width="80%" />
            <Skeleton width="60%" />
          </div>
        ) : (
          <EmptyState
            title="No team cost yet"
            description="Costs roll up to the team of a project's owner."
          />
        )}
      </CardPanel>

      <CardPanel title="Agent efficiency" subTitle="Per-agent cost, tokens and error rate">
        <TableWrap>
          <Table>
            <thead>
              <tr>
                <Th>Agent</Th>
                <Th align="right">Executions</Th>
                <Th align="right">Error rate</Th>
                <Th align="right">Cost</Th>
                <Th align="right">Tokens</Th>
              </tr>
            </thead>
            {agents.data?.items?.length ? (
              <tbody>
                {agents.data.items.map((a) => (
                  <Tr key={a.name}>
                    <Td className="table__cell--primary">{a.name}</Td>
                    <Td align="right" className="num">
                      {a.executions}
                    </Td>
                    <Td align="right" className="num">
                      <span className={a.error_rate ? "text-danger" : ""}>{formatPct(a.error_rate)}</span>
                    </Td>
                    <Td align="right" className="num">
                      {formatMoney(a.total_cost)}
                    </Td>
                    <Td align="right" className="num">
                      {formatTokens(a.total_tokens)}
                    </Td>
                  </Tr>
                ))}
              </tbody>
            ) : (
              <TableEmpty colSpan={5}>No agent spans seen yet.</TableEmpty>
            )}
          </Table>
        </TableWrap>
      </CardPanel>

      <div className="grid grid-2">
        <CardPanel
          title="Budgets"
          subTitle="Utilization against configured caps"
          extra={
            <Button
              variant="primary"
             
              onClick={() => setBudgetDialog({ open: true, budget: null })}
            >
              New budget
            </Button>
          }
        >
          {budgetError ? (
            <div style={{ padding: 16 }}>
              <QueryError what="the budget action" error={new Error(budgetError)} />
            </div>
          ) : null}
          {(budgets.data?.items ?? []).length ? (
            <div className="stack stack--loose" style={{ padding: "var(--global-dimension-size-200)" }}>
              {(budgets.data?.items ?? []).map((b) => {
                const pct = Math.round(b.utilization * 100);
                return (
                  <div key={b.id} className="row" style={{ gap: 12, alignItems: "center" }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <Progress
                        fraction={b.utilization}
                        label={
                          <>
                            {b.name ?? `Budget ${b.period}`}
                            <span className="muted"> · {b.scope}</span>
                            {b.period_type ? <span className="muted"> ({b.period_type})</span> : null}
                          </>
                        }
                        detail={`${formatMoney(b.spend)} / ${formatMoney(b.amount)} · ${pct}%`}
                      />
                    </div>
                    <Button
                      variant="quiet"
                     
                      onClick={() => setBudgetDialog({ open: true, budget: b })}
                    >
                      Edit
                    </Button>
                    <Button variant="danger" onClick={() => setDeletingBudget(b)}>
                      Delete
                    </Button>
                  </div>
                );
              })}
            </div>
          ) : budgets.isLoading ? (
            <div className="stack" style={{ padding: 16 }}>
              <Skeleton width="70%" />
              <Skeleton width="50%" />
            </div>
          ) : (
            <EmptyState
              title="No budgets configured"
              description="Track spend caps per department, team, project, client or workflow."
              extra={
                <Button
                  variant="primary"
                 
                  onClick={() => setBudgetDialog({ open: true, budget: null })}
                >
                  Create the first budget
                </Button>
              }
            />
          )}
        </CardPanel>

        <CardPanel
          title="Open alerts"
          subTitle={alerts.data ? `${alerts.data.total} open` : undefined}
        >
          {(alerts.data?.items ?? []).length ? (
            (alerts.data?.items ?? []).map((alert) => (
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
          ) : alerts.isLoading ? (
            <div className="stack" style={{ padding: 16 }}>
              <Skeleton width="60%" />
              <Skeleton width="80%" />
            </div>
          ) : (
            <EmptyState
              title="No open alerts"
              description="Nothing is crossing its configured threshold."
              extra={<Link to="/alerts">Configure rules</Link>}
            />
          )}
        </CardPanel>
      </div>

      <div className="grid grid-2">
        <CardPanel title="Consumption trend" subTitle="Cost per day">
          <div style={{ padding: "var(--global-dimension-size-100)" }}>
            <TrendChart
              data={trendSeries}
              series={[{ key: "total_cost", label: "Cost", type: "bar", colorIndex: 0 }]}
              valueFormatter={(v) => formatMoney(v)}
              height={220}
            />
          </div>
        </CardPanel>
        <CardPanel title="Tool calls per day" subTitle="Agent tool usage">
          <div style={{ padding: "var(--global-dimension-size-100)" }}>
            <TrendChart
              data={trendSeries}
              series={[{ key: "tool_calls", label: "Tool calls", colorIndex: 6 }]}
              height={220}
            />
          </div>
        </CardPanel>
      </div>

      {budgetDialog.open ? (
        <BudgetDialog
          key={budgetDialog.budget?.id ?? "new"}
          open
          budget={budgetDialog.budget}
          canCreateGlobal={canCreateGlobal}
          onClose={() => setBudgetDialog({ open: false, budget: null })}
          onSaved={refreshBudgets}
        />
      ) : null}

      <Dialog
        open={deletingBudget !== null}
        title="Delete budget"
        onClose={() => setDeletingBudget(null)}
        footer={
          <>
            <Button variant="danger" disabled={budgetBusy} onClick={() => void removeBudget()}>
              Delete budget
            </Button>
            <Button variant="quiet" onClick={() => setDeletingBudget(null)}>
              Cancel
            </Button>
          </>
        }
      >
        <p className="muted">
          {deletingBudget?.name ?? "This budget"} stops tracking and alerting
          immediately. Historical executions are not affected.
        </p>
      </Dialog>
    </div>
  );
}
