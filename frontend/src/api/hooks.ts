import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRefetchInterval } from "../state/RefreshContext";
import { api, type ExecutionQuery } from "./client";
import type { Filters } from "./types";

/**
 * Dashboard queries honour the persisted auto-refresh cadence (ticket 12);
 * detail/mutation-adjacent queries stay manual.
 */
export function useOverview(f: Filters) {
  const refetchInterval = useRefetchInterval();
  return useQuery({
    queryKey: ["overview", f],
    queryFn: () => api.overview(f),
    refetchInterval,
  });
}

export function useExecutions(f: Filters, opts: ExecutionQuery = {}) {
  const refetchInterval = useRefetchInterval();
  return useQuery({
    queryKey: ["executions", f, opts],
    queryFn: () => api.executions(f, opts),
    refetchInterval,
  });
}

export function useExecution(id: string) {
  return useQuery({
    queryKey: ["execution", id],
    queryFn: () => api.execution(id),
    enabled: !!id,
  });
}

export function useSpans(id: string) {
  return useQuery({
    queryKey: ["spans", id],
    queryFn: () => api.spans(id),
    enabled: !!id,
  });
}

export function useFailures(id: string) {
  return useQuery({
    queryKey: ["failures", id],
    queryFn: () => api.failures(id),
    enabled: !!id,
  });
}

export function useWorkflows(f: Filters) {
  const refetchInterval = useRefetchInterval();
  return useQuery({
    queryKey: ["workflows", f],
    queryFn: () => api.workflows(f),
    refetchInterval,
  });
}

export function useAgents(f: Filters) {
  const refetchInterval = useRefetchInterval();
  return useQuery({
    queryKey: ["agents", f],
    queryFn: () => api.agents(f),
    refetchInterval,
  });
}

export function useModels(f: Filters) {
  const refetchInterval = useRefetchInterval();
  return useQuery({
    queryKey: ["models", f],
    queryFn: () => api.models(f),
    refetchInterval,
  });
}

export function useTools(f: Filters) {
  const refetchInterval = useRefetchInterval();
  return useQuery({
    queryKey: ["tools", f],
    queryFn: () => api.tools(f),
    refetchInterval,
  });
}

export function useMargin(f: Filters, enabled = true) {
  const refetchInterval = useRefetchInterval();
  return useQuery({
    queryKey: ["margin", f],
    queryFn: () => api.margin(f),
    enabled,
    refetchInterval,
  });
}

export function useProjectRates(enabled = true) {
  return useQuery({
    queryKey: ["project-rates"],
    queryFn: () => api.projectRates.list(),
    enabled,
  });
}

export function useCosts(dimension: string, f: Filters) {
  const refetchInterval = useRefetchInterval();
  return useQuery({
    queryKey: ["costs", dimension, f],
    queryFn: () => api.costs(dimension, f),
    refetchInterval,
  });
}

export function useMetrics(dimension: string, f: Filters, key?: string) {
  const refetchInterval = useRefetchInterval();
  return useQuery({
    queryKey: ["metrics", dimension, key, f.days],
    queryFn: () => api.metrics(dimension, f, key),
    refetchInterval,
  });
}

export function useAlerts(
  enabled = true,
  params: {
    status?: string;
    severity?: string;
    q?: string;
    sort?: "triggered_at" | "severity";
    order?: "asc" | "desc";
    limit?: number;
  } = { status: "open" }
) {
  const refetchInterval = useRefetchInterval();
  return useQuery({
    queryKey: ["alerts", params],
    queryFn: () => api.alerts.list(params),
    enabled,
    refetchInterval,
  });
}

export function useAlertRules(enabled = true) {
  return useQuery({
    queryKey: ["alert-rules"],
    queryFn: () => api.alertRules.list(),
    enabled,
  });
}

export function useAlertChannels(enabled = true) {
  return useQuery({
    queryKey: ["alert-channels"],
    queryFn: () => api.alertChannels.list(),
    enabled,
  });
}

export function useAlertDeliveries(enabled = true) {
  return useQuery({
    queryKey: ["alert-deliveries"],
    queryFn: () => api.alertDeliveries.list({ limit: 50 }),
    enabled,
  });
}

export function useBudgetStatus() {
  const refetchInterval = useRefetchInterval();
  return useQuery({
    queryKey: ["budgets", "status"],
    queryFn: () => api.budgetStatus(),
    refetchInterval,
  });
}

export function useBudgets() {
  const refetchInterval = useRefetchInterval();
  return useQuery({
    queryKey: ["budgets", "list"],
    queryFn: () => api.budgets.list(),
    refetchInterval,
  });
}

export function useFailuresSeries(f: Filters, enabled = true) {
  const refetchInterval = useRefetchInterval();
  return useQuery({
    queryKey: ["failures-series", f],
    queryFn: () => api.failuresSeries(f),
    enabled,
    refetchInterval,
  });
}

export function useBudgetSeries(id: string | null) {
  return useQuery({
    queryKey: ["budget-series", id],
    queryFn: () => api.budgets.series(id as string),
    enabled: !!id,
  });
}

export function usePricing(params: {
  q?: string;
  sort?: "provider" | "model" | "effective_from";
  order?: "asc" | "desc";
}) {
  return useQuery({
    queryKey: ["pricing", params],
    queryFn: () => api.pricing.list(params),
  });
}

export function useDirectoryProjects() {
  return useQuery({
    queryKey: ["directory", "projects"],
    queryFn: () => api.directory.projects(),
  });
}

/**
 * Dimension rows (costs/usage) are keyed by the external `project_id`; the
 * dashboard renders the human name instead (ADR-0012). Keys missing from the
 * caller's visible directory fall back to the raw value.
 */
export function useProjectNameMap(): Map<string, string> {
  const projects = useDirectoryProjects();
  return useMemo(
    () =>
      new Map(
        (projects.data?.items ?? []).map((project) => [project.project_id, project.name])
      ),
    [projects.data]
  );
}

export function useDepartments() {
  return useQuery({
    queryKey: ["directory", "departments"],
    queryFn: () => api.directory.departments(),
  });
}

export function useTeams(departmentId?: string, mine = false) {
  return useQuery({
    queryKey: ["directory", "teams", departmentId ?? "all", mine ? "mine" : "all"],
    queryFn: () => api.directory.teams(departmentId, mine),
  });
}

/** The teams the caller belongs to (used when adding projects). */
export function useMyTeams() {
  return useTeams(undefined, true);
}

export function useRequests(view: "all" | "mine" | "to_approve", enabled = true) {
  return useQuery({
    queryKey: ["requests", view],
    queryFn: () => api.requests.list(view),
    enabled,
  });
}

export function usePendingApprovals(enabled: boolean) {
  return useQuery({
    queryKey: ["requests", "to_approve"],
    queryFn: () => api.requests.list("to_approve"),
    enabled,
  });
}

export function useProjectKeys(projectId: string, enabled = true) {
  return useQuery({
    queryKey: ["project-keys", projectId],
    queryFn: () => api.projects.keys(projectId),
    enabled: enabled && !!projectId,
  });
}

export function useUsers(enabled = true) {
  return useQuery({
    queryKey: ["users"],
    queryFn: () => api.users.list(),
    enabled,
  });
}
