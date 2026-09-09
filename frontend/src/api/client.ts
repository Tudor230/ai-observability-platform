import type { Filters, Overview, Execution, Span, FailureTree, AggregateRow, DayMetric, Alert, BudgetStatus } from "./types";

const BASE = import.meta.env.VITE_API_BASE || "/api/v1";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    throw new Error(`${res.status}: ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

export function qs(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") search.set(k, String(v));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export function filterQuery(f: Filters): string {
  return qs({ days: f.days, project_id: f.project_id, client_id: f.client_id, workflow: f.workflow });
}

interface List<T> {
  items: T[];
  total: number;
}

export const api = {
  get,
  overview: (f: Filters) => get<Overview>(`/overview${filterQuery(f)}`),
  executions: (f: Filters, status?: string, limit = 100, offset = 0) =>
    get<List<Execution>>(`/executions${qs({ ...f, status, limit, offset })}`),
  execution: (id: string) => get<Execution>(`/executions/${id}`),
  spans: (id: string) => get<List<Span>>(`/executions/${id}/spans`),
  failures: (id: string) => get<FailureTree>(`/executions/${id}/failures`),
  workflows: (f: Filters) => get<List<AggregateRow>>(`/workflows${filterQuery(f)}`),
  clients: (f: Filters) => get<List<AggregateRow>>(`/clients${filterQuery(f)}`),
  agents: (f: Filters) => get<List<AggregateRow>>(`/agents${filterQuery(f)}`),
  costs: (dimension: string, f: Filters) => get<List<AggregateRow>>(`/costs${qs({ dimension, ...f })}`),
  metrics: (dimension: string, key?: string) => get<List<DayMetric>>(`/metrics${qs({ dimension, dimension_key: key })}`),
  alerts: () => get<List<Alert>>(`/alerts?status=open`),
  budgetStatus: () => get<List<BudgetStatus>>(`/budgets/status`),
};
