import type {
  AccessRequest,
  AggregateRow,
  Alert,
  BudgetStatus,
  DayMetric,
  Department,
  DirectoryProject,
  Execution,
  FailureTree,
  Filters,
  Membership,
  Overview,
  Profile,
  ProjectKey,
  ProjectKeyRow,
  RequestList,
  RequestType,
  Role,
  ScopeType,
  Span,
  Team,
  UserAccount,
} from "./types";

const BASE = import.meta.env.VITE_API_BASE || "/api/v1";
const CSRF_HEADER = "x-requested-with";
const CSRF_VALUE = "aiobs";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

let onUnauthorized: (() => void) | null = null;

/** AuthContext registers this so a stale session drops to the login screen. */
export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  const headers = new Headers(init?.headers);
  if (method !== "GET" && method !== "HEAD" && method !== "OPTIONS") {
    headers.set(CSRF_HEADER, CSRF_VALUE);
  }
  if (init?.body && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
    ...init,
    headers,
  });
  if (res.status === 401) {
    onUnauthorized?.();
    throw new ApiError(401, "not authenticated");
  }
  if (!res.ok) {
    throw new ApiError(res.status, `${res.status}: ${await res.text()}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

const get = <T>(path: string) => request<T>(path);
const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
const del = <T>(path: string) => request<T>(path, { method: "DELETE" });

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

export interface ExecutionQuery {
  status?: string;
  /** Case-insensitive search over trace id, workflow and error message. */
  q?: string;
  sort?: "started_at" | "duration_ms" | "total_cost" | "total_tokens" | "error_count" | "status";
  order?: "asc" | "desc";
  limit?: number;
  offset?: number;
}

export const api = {
  get,
  overview: (f: Filters) => get<Overview>(`/overview${filterQuery(f)}`),
  executions: (f: Filters, opts: ExecutionQuery = {}) =>
    get<List<Execution>>(`/executions${qs({ ...f, limit: 100, ...opts })}`),
  execution: (id: string) => get<Execution>(`/executions/${id}`),
  spans: (id: string) => get<List<Span>>(`/executions/${id}/spans`),
  failures: (id: string) => get<FailureTree>(`/executions/${id}/failures`),
  workflows: (f: Filters) => get<List<AggregateRow>>(`/workflows${filterQuery(f)}`),
  clients: (f: Filters) => get<List<AggregateRow>>(`/clients${filterQuery(f)}`),
  agents: (f: Filters) => get<List<AggregateRow>>(`/agents${filterQuery(f)}`),
  costs: (dimension: string, f: Filters) => get<List<AggregateRow>>(`/costs${qs({ dimension, ...f })}`),
  metrics: (dimension: string, f: Filters, key?: string) =>
    get<List<DayMetric>>(`/metrics${qs({ dimension, dimension_key: key, days: f.days })}`),
  alerts: () => get<List<Alert>>(`/alerts?status=open`),
  budgetStatus: () => get<List<BudgetStatus>>(`/budgets/status`),

  auth: {
    me: () => get<Profile>("/auth/me"),
    login: (email: string, password: string) =>
      post<Profile>("/auth/login", { email, password }),
    logout: () => post<{ ok: boolean }>("/auth/logout"),
  },

  directory: {
    projects: () => get<List<DirectoryProject>>("/projects"),
    departments: () => get<List<Department>>("/departments"),
    teams: () => get<List<Team>>("/teams"),
  },

  requests: {
    list: (view?: "all" | "mine" | "to_approve") =>
      get<RequestList>(`/requests${qs({ view })}`),
    create: (type: RequestType, payload: Record<string, unknown>) =>
      post<AccessRequest>("/requests", { type, payload }),
    approve: (id: string) => post<{ id: string; status: string }>(`/requests/${id}/approve`),
    reject: (id: string, reason: string) =>
      post<{ id: string; status: string; reason: string }>(`/requests/${id}/reject`, { reason }),
    cancel: (id: string) => post<{ id: string; status: string }>(`/requests/${id}/cancel`),
  },

  projects: {
    keys: (projectId: string) =>
      get<List<ProjectKeyRow>>(`/projects/${projectId}/keys`),
    createKey: (projectId: string, label?: string) =>
      post<ProjectKey>(`/projects/${projectId}/keys`, { label: label || null }),
    rotateKey: (projectId: string, keyId: string) =>
      post<ProjectKey>(`/projects/${projectId}/keys/${keyId}/rotate`),
    revokeKey: (projectId: string, keyId: string) =>
      del<{ id: string; active: boolean }>(`/projects/${projectId}/keys/${keyId}`),
  },

  users: {
    list: () => get<List<UserAccount>>("/users"),
    create: (email: string, password?: string) =>
      post<{ id: string; email: string; api_key: string; password: string }>(
        "/users",
        { email, password: password || null }
      ),
    resetPassword: (userId: string) =>
      post<{ id: string; email: string; password: string }>(
        `/users/${userId}/reset-password`
      ),
    disable: (userId: string) =>
      post<{ id: string; enabled: boolean }>(`/users/${userId}/disable`),
    enable: (userId: string) =>
      post<{ id: string; enabled: boolean }>(`/users/${userId}/enable`),
    grantMembership: (
      userId: string,
      role: Role,
      scopeType: ScopeType,
      scopeId: string | null
    ) =>
      post<Membership>(`/users/${userId}/memberships`, {
        role,
        scope_type: scopeType,
        scope_id: scopeId,
      }),
    revokeMembership: (userId: string, membershipId: string) =>
      del<{ id: string; status: string }>(
        `/users/${userId}/memberships/${membershipId}`
      ),
  },
};
