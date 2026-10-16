import { useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  useAgents,
  useAlerts,
  useBudgetSeries,
  useBudgetStatus,
  useCosts,
  useMetrics,
  useOverview,
  useProjectNameMap,
} from "../api/hooks";
import { api } from "../api/client";
import type { BudgetStatus } from "../api/types";
import { useAuth } from "../state/AuthContext";
import { useFilters } from "../state/FiltersContext";
import { PageHeader } from "../components/PageHeader";
import { FilterChips, FiltersControl } from "../components/FiltersControl";
import { RefreshButton } from "../components/RefreshButton";
import { BudgetDialog } from "../components/BudgetDialog";
import { TrendChart } from "../components/charts/TrendChart";
import { CostCard, CostCardBars } from "../components/CostCard";
import { TableFilterChips, TableFilters } from "../components/TableFilters";
import { useTableFilters } from "../state/useTableFilters";
import { SeverityBadge } from "../components/domain";
import {
  Button,
  CardPanel,
  Delta,
  Dialog,
  EmptyState,
  Metric,
  Progress,
  QueryError,
  Skeleton,
  useToast,
} from "../components/core";
import {
  formatMoney,
  formatMs,
  formatPct,
  formatTokens,
  formatUnitCost,
} from "../lib/format";

export default function Manager() {
  const { filters } = useFilters();
  const { hasRole } = useAuth();
  const queryClient = useQueryClient();
  const overview = useOverview(filters);
  // Every card owns its own filters (namespaced URL state, refinements v3).
  const workflowCard = useTableFilters("workflows");
  const projectCard = useTableFilters("projects");
  const teamCard = useTableFilters("teams");
  const agentCard = useTableFilters("agents");
  const costsByWorkflow = useCosts("workflow", { ...filters, ...workflowCard.filters });
  const costsByProject = useCosts("project", { ...filters, ...projectCard.filters });
  const costsByTeam = useCosts("team", { ...filters, ...teamCard.filters });
  const projectNames = useProjectNameMap();
  const agents = useAgents({ ...filters, ...agentCard.filters });
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
  const [burningDown, setBurningDown] = useState<BudgetStatus | null>(null);
  const [budgetBusy, setBudgetBusy] = useState(false);
  const [budgetError, setBudgetError] = useState<string | null>(null);
  const burnSeries = useBudgetSeries(burningDown?.id ?? null);
  const burn = burnSeries.data;
  const burnRows = burn
    ? burn.items.map((point) => ({
        day: point.day.slice(5),
        cumulative: point.cumulative,
        cap: burn.amount,
      }))
    : [];

  const overviewData = overview.data;
  const metricItems = trends.data?.items ?? [];
  const worstBudget = (budgets.data?.items ?? [])
    .slice()
    .sort((a, b) => b.utilization - a.utilization)[0];
  const budgetCount = budgets.data?.items?.length ?? 0;
  const costPerExecution = overviewData?.executions
    ? (overviewData.total_cost ?? 0) / overviewData.executions
    : null;
  const inputTokens = metricItems.reduce((sum, m) => sum + (m.input_tokens ?? 0), 0);
  const outputTokens = metricItems.reduce((sum, m) => sum + (m.output_tokens ?? 0), 0);

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
    overview.error ?? costsByWorkflow.error ?? costsByProject.error ?? agents.error;
  const anyError =
    overview.isError ||
    costsByWorkflow.isError ||
    costsByProject.isError ||
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
        subTitle="Spend by workflow and project, budget health and agent efficiency."
        extra={
          <>
            <FiltersControl dimensions={["days"]} />
            <RefreshButton />
          </>
        }
      />
      <FilterChips dimensions={["days"]} />

      {anyError ? <QueryError what="manager data" error={loadError} /> : null}

      {overview.isLoading ? (
        <div className="grid grid-4">
          {Array.from({ length: 8 }, (_, i) => (
            <Skeleton key={i} shape="chart" />
          ))}
        </div>
      ) : (
        <div className="grid grid-4">
          <Metric
            label="Total cost"
            value={formatMoney(overviewData?.total_cost)}
            sub={<Delta pct={overviewData?.deltas?.total_cost_pct} polarity="up-is-bad" />}
          />
          <Metric
            label="Executions"
            value={overviewData?.executions ?? 0}
            sub={
              <>
                {overviewData?.failed_executions ?? 0} failed{" "}
                <Delta pct={overviewData?.deltas?.executions_pct} polarity="down-is-bad" />
              </>
            }
          />
          <Metric
            label="Error rate"
            value={formatPct(overviewData?.error_rate)}
            tone={overviewData?.error_rate ? "danger" : "default"}
            sub={<Delta pct={overviewData?.deltas?.error_rate_pct} polarity="up-is-bad" />}
          />
          <Metric
            label="Open alerts"
            value={alerts.data?.total ?? 0}
            tone={alerts.data?.total ? "warning" : "default"}
          />
          <Metric
            label="p95 latency"
            value={formatMs(overviewData?.p95_duration_ms)}
            sub={`p50 ${formatMs(overviewData?.p50_duration_ms)}`}
          />
          <Metric label="Cost per execution" value={formatUnitCost(costPerExecution)} />
          <Metric
            label="Tokens"
            value={formatTokens(overviewData?.total_tokens)}
            sub={`${formatTokens(inputTokens)} in / ${formatTokens(outputTokens)} out`}
          />
          <Metric
            label="Budget utilization"
            value={worstBudget ? formatPct(worstBudget.utilization) : "—"}
            sub={budgetCount ? `${budgetCount} budget${budgetCount === 1 ? "" : "s"}` : "no budgets"}
            tone={worstBudget && worstBudget.utilization >= 0.8 ? "warning" : "default"}
          />
        </div>
      )}

      <div className="grid grid-2">
        <CostCard
          filters={<TableFilters card="workflows" title="Workflows" />}
          filterChips={<TableFilterChips card="workflows" />}
          title="Workflows"
          subTitle="Cost, reliability and volume per workflow"
          loading={costsByWorkflow.isLoading}
          emptyBreakdown="No workflow cost yet"
          emptyDetail="No workflows in range."
          columns={["Workflow", "Executions", "Error rate", "Tokens", "Cost"]}
          rows={(costsByWorkflow.data?.items ?? []).map((item) => {
            const key = item.key ?? String(item.name);
            const label = item.key ?? item.name ?? "—";
            return {
              key,
              href: `/engineering?workflow=${encodeURIComponent(key)}`,
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
          filters={<TableFilters card="projects" title="Projects" />}
          filterChips={<TableFilterChips card="projects" />}
          title="Projects"
          subTitle="Cost, reliability and volume per project"
          loading={costsByProject.isLoading}
          emptyBreakdown="No project cost yet"
          emptyDetail="No project spend in range."
          columns={["Project", "Executions", "Error rate", "Tokens", "Cost"]}
          rows={(costsByProject.data?.items ?? []).map((item) => {
            const key = item.key ?? String(item.name);
            const label = projectNames.get(item.key ?? "") ?? item.key ?? item.name ?? "—";
            return {
              key,
              href: `/engineering?project_id=${encodeURIComponent(key)}`,
              bar: {
                label,
                value: item.total_cost ?? 0,
                valueLabel: formatMoney(item.total_cost),
                sublabel: `${item.executions} executions · ${formatTokens(item.total_tokens)} tokens`,
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
      </div>

      <CostCard
        filters={<TableFilters card="teams" title="Teams" />}
        filterChips={<TableFilterChips card="teams" />}
        title="Teams"
        subTitle="Spend per team in your scope"
        loading={costsByTeam.isLoading}
        emptyBreakdown="No team cost yet"
        emptyDetail="No team spend in range."
        columns={["Team", "Executions", "Error rate", "Tokens", "Cost"]}
        rows={(costsByTeam.data?.items ?? []).map((item) => {
          const key = item.key ?? String(item.name);
          const label = item.key ?? item.name ?? "unassigned";
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
        filters={<TableFilters card="agents" title="Agents" />}
        filterChips={<TableFilterChips card="agents" />}
        title="Agents"
        subTitle="Per-agent cost, tokens and error rate"
        loading={agents.isLoading}
        emptyBreakdown="No agent spans seen yet"
        emptyDetail="No agents in range."
        columns={["Agent", "Executions", "Error rate", "Tokens", "Cost"]}
        rows={(agents.data?.items ?? []).map((a) => {
          const label = a.name ?? "unknown";
          return {
            key: label,
            bar: {
              label,
              value: a.total_cost ?? 0,
              valueLabel: formatMoney(a.total_cost),
              sublabel: `${a.executions} executions`,
            },
            cells: [
              label,
              a.executions,
              <span className={a.error_rate ? "text-danger" : ""}>{formatPct(a.error_rate)}</span>,
              formatTokens(a.total_tokens),
              formatMoney(a.total_cost),
            ],
            sortValues: [
              label,
              a.executions,
              a.error_rate ?? 0,
              a.total_tokens,
              a.total_cost ?? 0,
            ],
          };
        })}
        breakdown={(visible) => <CostCardBars rows={visible} />}
      />

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
                    <Button variant="quiet" onClick={() => setBurningDown(b)}>
                      Burn-down
                    </Button>
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
              description="Track spend caps per department, team, project or workflow."
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
      <Dialog
        open={burningDown !== null}
        title="Budget burn-down"
        onClose={() => setBurningDown(null)}
        footer={
          <Button variant="quiet" onClick={() => setBurningDown(null)}>
            Close
          </Button>
        }
      >
        {burnSeries.isError ? (
          <QueryError what="the budget series" error={burnSeries.error} />
        ) : burnSeries.isLoading || !burn ? (
          <Skeleton shape="chart" />
        ) : (
          <>
            <p className="muted" style={{ margin: 0 }}>
              {burn.budget.name ?? "Budget"} · cap {formatMoney(burn.amount)} ·{" "}
              {burn.period_start.slice(0, 10)} → {burn.period_end.slice(0, 10)}
            </p>
            <TrendChart
              data={burnRows}
              series={[
                { key: "cumulative", label: "Spent", colorIndex: 0 },
                { key: "cap", label: "Budget cap", colorIndex: 3, dashed: true },
              ]}
              valueFormatter={(v) => formatMoney(v)}
              height={240}
            />
          </>
        )}
      </Dialog>
    </div>
  );
}
