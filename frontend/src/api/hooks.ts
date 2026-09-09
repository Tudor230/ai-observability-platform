import { useQuery } from "@tanstack/react-query";
import { api } from "./client";
import type { Filters } from "./types";

export function useOverview(f: Filters) {
  return useQuery({
    queryKey: ["overview", f],
    queryFn: () => api.overview(f),
  });
}

export function useExecutions(f: Filters, status?: string) {
  return useQuery({
    queryKey: ["executions", f, status],
    queryFn: () => api.executions(f, status),
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

export function useMetrics(dimension: string, key?: string) {
  return useQuery({
    queryKey: ["metrics", dimension, key],
    queryFn: () => api.metrics(dimension, key),
  });
}

export function useAlerts() {
  return useQuery({ queryKey: ["alerts"], queryFn: () => api.alerts() });
}

export function useBudgetStatus() {
  return useQuery({ queryKey: ["budgets", "status"], queryFn: () => api.budgetStatus() });
}
