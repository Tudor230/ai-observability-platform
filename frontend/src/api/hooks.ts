import { useQuery } from "@tanstack/react-query";
import { api, type ExecutionQuery } from "./client";
import type { Filters } from "./types";

export function useOverview(f: Filters) {
  return useQuery({
    queryKey: ["overview", f],
    queryFn: () => api.overview(f),
  });
}

export function useExecutions(f: Filters, opts: ExecutionQuery = {}) {
  return useQuery({
    queryKey: ["executions", f, opts],
    queryFn: () => api.executions(f, opts),
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
  return useQuery({ queryKey: ["workflows", f], queryFn: () => api.workflows(f) });
}

export function useClients(f: Filters) {
  return useQuery({ queryKey: ["clients", f], queryFn: () => api.clients(f) });
}

export function useAgents(f: Filters) {
  return useQuery({ queryKey: ["agents", f], queryFn: () => api.agents(f) });
}

export function useCosts(dimension: string, f: Filters) {
  return useQuery({
    queryKey: ["costs", dimension, f],
    queryFn: () => api.costs(dimension, f),
  });
}

export function useMetrics(dimension: string, f: Filters, key?: string) {
  return useQuery({
    queryKey: ["metrics", dimension, key, f.days],
    queryFn: () => api.metrics(dimension, f, key),
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
  return useQuery({
    queryKey: ["alerts", params],
    queryFn: () => api.alerts.list(params),
    enabled,
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

export function useBudgetStatus() {
  return useQuery({ queryKey: ["budgets", "status"], queryFn: () => api.budgetStatus() });
}

export function useBudgets() {
  return useQuery({ queryKey: ["budgets", "list"], queryFn: () => api.budgets.list() });
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

export function useDepartments() {
  return useQuery({
    queryKey: ["directory", "departments"],
    queryFn: () => api.directory.departments(),
  });
}

export function useTeams(departmentId?: string) {
  return useQuery({
    queryKey: ["directory", "teams", departmentId ?? "all"],
    queryFn: () => api.directory.teams(departmentId),
  });
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
