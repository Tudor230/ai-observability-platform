import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { renderWithProviders, profile } from "../test/harness";

const h = vi.hoisted(() => ({
  me: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  overview: vi.fn(),
  executions: vi.fn(),
  execution: vi.fn(),
  spans: vi.fn(),
  failures: vi.fn(),
  workflows: vi.fn(),
  clients: vi.fn(),
  agents: vi.fn(),
  costs: vi.fn(),
  metrics: vi.fn(),
  alertsList: vi.fn(),
  alertsUpdate: vi.fn(),
  rulesList: vi.fn(),
  rulesCreate: vi.fn(),
  rulesUpdate: vi.fn(),
  rulesRemove: vi.fn(),
  channelsList: vi.fn(),
  channelsCreate: vi.fn(),
  channelsUpdate: vi.fn(),
  channelsRemove: vi.fn(),
  budgetStatus: vi.fn(),
  budgetCreate: vi.fn(),
  budgetUpdate: vi.fn(),
  budgetRemove: vi.fn(),
  pricingList: vi.fn(),
  pricingCreate: vi.fn(),
  pricingRemove: vi.fn(),
  dirProjects: vi.fn(),
  dirDepartments: vi.fn(),
  dirTeams: vi.fn(),
  requestsList: vi.fn(),
  requestsCreate: vi.fn(),
  requestsApprove: vi.fn(),
  requestsReject: vi.fn(),
  requestsCancel: vi.fn(),
  keysList: vi.fn(),
  keysCreate: vi.fn(),
  keysRotate: vi.fn(),
  keysRevoke: vi.fn(),
  usersList: vi.fn(),
  usersCreate: vi.fn(),
  usersReset: vi.fn(),
  usersDisable: vi.fn(),
  usersEnable: vi.fn(),
  usersGrant: vi.fn(),
  usersRevoke: vi.fn(),
}));

vi.mock("../api/client", () => ({
  ApiError: class ApiError extends Error {
    constructor(
      public status: number,
      message: string
    ) {
      super(message);
    }
  },
  setUnauthorizedHandler: vi.fn(),
  api: {
    auth: { me: h.me, login: h.login, logout: h.logout },
    overview: h.overview,
    executions: h.executions,
    execution: h.execution,
    spans: h.spans,
    failures: h.failures,
    workflows: h.workflows,
    clients: h.clients,
    agents: h.agents,
    costs: h.costs,
    metrics: h.metrics,
    alerts: { list: h.alertsList, update: h.alertsUpdate },
    alertRules: {
      list: h.rulesList,
      create: h.rulesCreate,
      update: h.rulesUpdate,
      remove: h.rulesRemove,
    },
    alertChannels: {
      list: h.channelsList,
      create: h.channelsCreate,
      update: h.channelsUpdate,
      remove: h.channelsRemove,
    },
    budgetStatus: h.budgetStatus,
    budgets: {
      list: h.budgetStatus,
      create: h.budgetCreate,
      update: h.budgetUpdate,
      remove: h.budgetRemove,
    },
    pricing: { list: h.pricingList, create: h.pricingCreate, remove: h.pricingRemove },
    directory: {
      projects: h.dirProjects,
      departments: h.dirDepartments,
      teams: h.dirTeams,
    },
    requests: {
      list: h.requestsList,
      create: h.requestsCreate,
      approve: h.requestsApprove,
      reject: h.requestsReject,
      cancel: h.requestsCancel,
    },
    projects: {
      keys: h.keysList,
      createKey: h.keysCreate,
      rotateKey: h.keysRotate,
      revokeKey: h.keysRevoke,
    },
    users: {
      list: h.usersList,
      create: h.usersCreate,
      resetPassword: h.usersReset,
      disable: h.usersDisable,
      enable: h.usersEnable,
      grantMembership: h.usersGrant,
      revokeMembership: h.usersRevoke,
    },
  },
}));

import Overview from "./Overview";
import Engineering from "./Engineering";
import ExecutionDetail from "./ExecutionDetail";
import Manager from "./Manager";
import Executive from "./Executive";
import Client from "./Client";
import Projects from "./Projects";
import Project from "./Project";
import Requests from "./Requests";
import Accounts from "./Accounts";
import PricingPage from "./Pricing";
import AlertsPage from "./Alerts";
import Login from "./Login";

const overview = {
  executions: 12,
  failed_executions: 2,
  error_rate: 0.1667,
  total_cost: 1.23,
  total_tokens: 4500,
  llm_calls: 8,
  tool_calls: 4,
  avg_duration_ms: 1200,
  p50_duration_ms: 1000,
  p95_duration_ms: 3000,
  p99_duration_ms: 4200,
  deltas: { total_cost_pct: 12.5, executions_pct: -3.2, error_rate_pct: 1.1 },
  open_alerts: 1,
};

const dayMetric = {
  day: "2026-10-01",
  dimension: "total",
  dimension_key: null,
  executions: 4,
  failed_executions: 1,
  error_rate: 0.25,
  total_tokens: 1500,
  input_tokens: 1000,
  output_tokens: 500,
  llm_calls: 3,
  tool_calls: 2,
  total_cost: 0.4,
  avg_duration_ms: 1200,
  p50_duration_ms: 900,
  p95_duration_ms: 2500,
  p99_duration_ms: 3000,
};

const execution = {
  id: "e1",
  trace_id: "trace-1",
  workflow_id: "wf-1",
  session_id: "wf-1",
  project_id: "p1",
  client_id: "client-42",
  workflow: "checkout",
  workflow_version: "v2",
  status: "ok",
  error_kind: null,
  error_message: null,
  metadata: { channel: "web" },
  started_at: "2026-10-01T10:00:00Z",
  ended_at: "2026-10-01T10:00:02Z",
  duration_ms: 2000,
  total_cost: 0.01,
  input_tokens: 100,
  output_tokens: 50,
  total_tokens: 150,
  llm_calls: 1,
  tool_calls: 1,
  retrieval_calls: 0,
  agent_calls: 0,
  error_count: 0,
  retry_count: 0,
  unpriced_calls: 0,
  cost_complete: true,
};

const aggregate = {
  key: "checkout",
  name: "checkout",
  executions: 5,
  failed_executions: 1,
  error_rate: 0.2,
  total_cost: 0.5,
  total_tokens: 900,
  llm_calls: 4,
  avg_duration_ms: 800,
  last_seen: "2026-10-01T10:00:00Z",
};

const alert = {
  id: "a1",
  rule_id: "rule:1",
  rule_ref: "rule-1",
  severity: "warning",
  message: "Error rate 60% today exceeds 50%",
  dimension: "rule",
  dimension_key: "error_rate",
  status: "open",
  triggered_at: "2026-10-01T10:00:00Z",
  scope: "team",
  scope_name: "A",
  can_ack: true,
};

const budget = {
  id: "b1",
  name: "Team cap",
  amount: 100,
  spend: 62,
  utilization: 0.62,
  period: "2026-10-01",
  period_type: "month",
  period_start: "2026-10-01T00:00:00Z",
  period_end: "2026-11-01T00:00:00Z",
  workflow_name: null,
  project: null,
  client: null,
  department: null,
  team: "A",
  scope: "team",
};

const pricingRow = {
  id: "pr1",
  provider: "openai",
  model: "gpt-4o-mini",
  model_match: "exact",
  input_price_per_1m: 0.15,
  output_price_per_1m: 0.6,
  cache_read_price_per_1m: 0.075,
  cache_write_price_per_1m: null,
  reasoning_price_per_1m: null,
  currency: "USD",
  effective_from: "2026-10-01T00:00:00Z",
};

const rule = {
  id: "rule-1",
  name: "Error rate",
  metric: "error_rate",
  warning_threshold: 0.5,
  critical_threshold: 1,
  scope_type: "global",
  scope_id: null,
  scope_name: "Global",
  enabled: true,
  builtin: true,
  channel_ids: [],
  created_at: "2026-10-01T00:00:00Z",
};

const channel = {
  id: "ch1",
  name: "Ops email",
  type: "email",
  target: "ops@example.com",
  enabled: true,
  created_at: "2026-10-01T00:00:00Z",
};

const projectRow = {
  id: "p1",
  project_id: "p1",
  name: "Checkout",
  enabled: true,
  has_keys: true,
  active_keys: 1,
  team_id: "t1",
  team_name: "A",
  department_id: "d1",
  department_name: "Ops",
};

function requestItem(overrides: Record<string, unknown> = {}) {
  return {
    id: "r1",
    type: "membership",
    status: "pending",
    payload: { role: "engineer", scope_type: "team", scope_id: "t1" },
    requester_id: "u2",
    requester_email: "eng@test",
    approver_id: null,
    approver_email: null,
    reason: null,
    created_at: "2026-10-01T10:00:00Z",
    decided_at: null,
    mine: false,
    can_approve: true,
    ...overrides,
  };
}

function resetMocks() {
  Object.values(h).forEach((mock) => mock.mockReset());
  h.me.mockResolvedValue(profile(["admin"]));
  h.overview.mockResolvedValue(overview);
  h.executions.mockResolvedValue({ items: [execution], total: 1, limit: 100, offset: 0 });
  h.execution.mockResolvedValue(execution);
  h.spans.mockResolvedValue({ items: [], total: 0 });
  h.failures.mockResolvedValue({ execution_id: "e1", error_count: 0, nodes: [] });
  h.workflows.mockResolvedValue({ items: [aggregate], total: 1 });
  h.clients.mockResolvedValue({ items: [aggregate], total: 1 });
  h.agents.mockResolvedValue({ items: [aggregate], total: 1 });
  h.costs.mockResolvedValue({ items: [aggregate], total: 1 });
  h.metrics.mockResolvedValue({ items: [dayMetric], total: 1 });
  h.alertsList.mockResolvedValue({ items: [alert], total: 1 });
  h.alertsUpdate.mockResolvedValue({ id: "a1", status: "acknowledged" });
  h.rulesList.mockResolvedValue({ items: [rule], total: 1 });
  h.rulesUpdate.mockResolvedValue(rule);
  h.rulesCreate.mockResolvedValue(rule);
  h.rulesRemove.mockResolvedValue({ deleted: "rule-1" });
  h.channelsList.mockResolvedValue({ items: [channel], total: 1 });
  h.channelsCreate.mockResolvedValue(channel);
  h.channelsUpdate.mockResolvedValue(channel);
  h.channelsRemove.mockResolvedValue({ deleted: "ch1" });
  h.budgetStatus.mockResolvedValue({ items: [budget], total: 1 });
  h.budgetCreate.mockResolvedValue(budget);
  h.budgetUpdate.mockResolvedValue(budget);
  h.budgetRemove.mockResolvedValue({ deleted: "b1" });
  h.pricingList.mockResolvedValue({ items: [pricingRow], total: 1 });
  h.pricingCreate.mockResolvedValue({ id: "pr2", effective_from: "2026-10-01T00:00:00Z" });
  h.pricingRemove.mockResolvedValue({ deleted: "pr1" });
  h.dirProjects.mockResolvedValue({ items: [projectRow], total: 1 });
  h.dirDepartments.mockResolvedValue({ items: [{ id: "d1", name: "Ops" }], total: 1 });
  h.dirTeams.mockResolvedValue({
    items: [{ id: "t1", name: "A", department_id: "d1", department_name: "Ops" }],
    total: 1,
  });
  h.requestsList.mockResolvedValue({ items: [requestItem()], total: 1, pending_approvals: 1 });
  h.requestsCreate.mockResolvedValue(requestItem({ status: "approved", mine: true }));
  h.requestsApprove.mockResolvedValue({ id: "r1", status: "approved" });
  h.requestsReject.mockResolvedValue({ id: "r1", status: "rejected", reason: "no" });
  h.requestsCancel.mockResolvedValue({ id: "r1", status: "cancelled" });
  h.keysList.mockResolvedValue({
    items: [
      {
        id: "k1",
        label: "prod",
        hint: "…abcd",
        active: true,
        created_at: "2026-10-01T00:00:00Z",
        last_used_at: null,
        revoked_at: null,
      },
    ],
    total: 1,
  });
  h.keysCreate.mockResolvedValue({ id: "k2", api_key: "plaintext-key", label: "new" });
  h.keysRotate.mockResolvedValue({ id: "k1", api_key: "rotated-key", label: "prod" });
  h.keysRevoke.mockResolvedValue({ id: "k1", active: false });
  h.usersList.mockResolvedValue({
    items: [
      {
        id: "u2",
        email: "eng@test",
        enabled: true,
        roles: ["engineer"],
        memberships: [
          { id: "m1", role: "engineer", scope_type: "team", scope_id: "t1", scope_name: "A", status: "approved", created_at: null },
        ],
        created_at: null,
      },
    ],
    total: 1,
  });
  h.usersCreate.mockResolvedValue({ id: "u3", email: "new@test", api_key: "k", password: "pw" });
  h.usersReset.mockResolvedValue({ id: "u2", email: "eng@test", password: "new-pw" });
  h.usersDisable.mockResolvedValue({ id: "u2", enabled: false });
  h.usersEnable.mockResolvedValue({ id: "u2", enabled: true });
  h.usersGrant.mockResolvedValue({ id: "m2", role: "manager", scope_type: "team", scope_id: "t1", scope_name: "A", status: "approved", created_at: null });
  h.usersRevoke.mockResolvedValue({ id: "m1", status: "revoked" });
  h.login.mockResolvedValue(profile(["engineer"]));
  h.logout.mockResolvedValue({ ok: true });
}

beforeEach(resetMocks);

describe("Overview", () => {
  it("renders KPIs, new trend panels and alerts", async () => {
    renderWithProviders(<Overview />);
    expect(await screen.findByText("Total cost")).toBeInTheDocument();
    expect(screen.getByText("$1.23")).toBeInTheDocument();
    expect(screen.getByText("Latency over time")).toBeInTheDocument();
    expect(screen.getByText("Error rate over time")).toBeInTheDocument();
    expect(screen.getAllByText("Open alerts").length).toBeGreaterThan(0);
    expect(screen.getByText(/Error rate 60%/)).toBeInTheDocument();
  });
});

describe("Engineering", () => {
  it("renders the execution list", async () => {
    renderWithProviders(<Engineering />);
    expect(await screen.findByRole("link", { name: /checkout/ })).toBeInTheDocument();
    expect(screen.getByText("client-42")).toBeInTheDocument();
  });

  it("sorts server-side when a header is clicked", async () => {
    renderWithProviders(<Engineering />);
    fireEvent.click(await screen.findByRole("button", { name: /Cost/ }));
    await waitFor(() =>
      expect(h.executions).toHaveBeenLastCalledWith(
        expect.anything(),
        expect.objectContaining({ sort: "total_cost", order: "desc" })
      )
    );
  });

  it("paginates with Next", async () => {
    h.executions.mockResolvedValue({
      items: [execution],
      total: 250,
      limit: 100,
      offset: 0,
    });
    renderWithProviders(<Engineering />);
    fireEvent.click(await screen.findByRole("button", { name: "Next" }));
    await waitFor(() =>
      expect(h.executions).toHaveBeenLastCalledWith(
        expect.anything(),
        expect.objectContaining({ offset: 100 })
      )
    );
  });

  it("shows the empty state with a Requests link", async () => {
    h.executions.mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 });
    renderWithProviders(<Engineering />);
    expect(await screen.findByText(/No executions in range/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Register a project" })).toBeInTheDocument();
  });
});

describe("ExecutionDetail", () => {
  const Routed = () => (
    <Routes>
      <Route path="/engineering/:id" element={<ExecutionDetail />} />
    </Routes>
  );

  it("renders execution KPIs and tabs", async () => {
    renderWithProviders(<Routed />, { route: "/engineering/e1" });
    expect(await screen.findByText("checkout")).toBeInTheDocument();
    expect(screen.getByText("fully priced")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Failures/ })).toBeInTheDocument();
  });

  it("shows a not-found state for a 404", async () => {
    h.execution.mockRejectedValue(new Error("404: nope"));
    renderWithProviders(<Routed />, { route: "/engineering/missing" });
    expect(await screen.findByText("Execution not found.")).toBeInTheDocument();
  });
});

describe("Manager", () => {
  it("renders cost panels, budgets and alerts", async () => {
    renderWithProviders(<Manager />);
    expect(await screen.findByText("Cost by workflow")).toBeInTheDocument();
    expect(screen.getByText("Cost by team")).toBeInTheDocument();
    expect(screen.getByText("Tool calls per day")).toBeInTheDocument();
    expect(screen.getByText("Team cap")).toBeInTheDocument();
  });

  it("creates a budget from the dialog", async () => {
    renderWithProviders(<Manager />);
    fireEvent.click(await screen.findByRole("button", { name: "New budget" }));
    fireEvent.change(screen.getByPlaceholderText("e.g. Team A monthly cap"), {
      target: { value: "My cap" },
    });
    fireEvent.change(screen.getByPlaceholderText("100"), { target: { value: "50" } });
    fireEvent.click(screen.getByRole("button", { name: "Create budget" }));
    await waitFor(() =>
      expect(h.budgetCreate).toHaveBeenCalledWith(
        expect.objectContaining({ name: "My cap", amount: 50 })
      )
    );
  });
});

describe("Executive", () => {
  it("renders unit economics, forecast and model chart", async () => {
    renderWithProviders(<Executive />);
    expect(await screen.findByText("Total AI cost")).toBeInTheDocument();
    expect(screen.getAllByText("Cost by model").length).toBeGreaterThan(0);
    expect(screen.getByText("Forecast")).toBeInTheDocument();
  });
});

describe("Client", () => {
  it("renders the client view without cost fields", async () => {
    h.me.mockResolvedValue(profile(["client"]));
    renderWithProviders(<Client />);
    expect(await screen.findByText("Executions & errors")).toBeInTheDocument();
    expect(screen.queryByText("Total cost")).not.toBeInTheDocument();
    expect(screen.queryByText("Cost")).not.toBeInTheDocument();
  });
});

describe("Projects + Project", () => {
  it("lists visible projects", async () => {
    renderWithProviders(<Projects />);
    expect(await screen.findByText("Checkout")).toBeInTheDocument();
    expect(screen.getByText("A")).toBeInTheDocument();
  });

  it("renders the project page with keys and charts", async () => {
    const Routed = () => (
      <Routes>
        <Route path="/projects/:projectId" element={<Project />} />
      </Routes>
    );
    renderWithProviders(<Routed />, { route: "/projects/p1" });
    expect(await screen.findByText("p1 · Checkout")).toBeInTheDocument();
    expect(screen.getByText("Executions over time")).toBeInTheDocument();
    expect(screen.getByText("Cost over time")).toBeInTheDocument();
    expect(await screen.findByText("prod")).toBeInTheDocument();
  });

  it("adds an ingest key and reveals it once", async () => {
    const Routed = () => (
      <Routes>
        <Route path="/projects/:projectId" element={<Project />} />
      </Routes>
    );
    renderWithProviders(<Routed />, { route: "/projects/p1" });
    fireEvent.click(await screen.findByRole("button", { name: /Add key/ }));
    await waitFor(() => expect(h.keysCreate).toHaveBeenCalled());
    expect(await screen.findByText("plaintext-key")).toBeInTheDocument();
  });
});

describe("Requests", () => {
  it("renders the approvals tab for approvers", async () => {
    renderWithProviders(<Requests />);
    expect(await screen.findByRole("tab", { name: /Approvals/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /New request/ })).toBeInTheDocument();
  });

  it("approves a pending request", async () => {
    renderWithProviders(<Requests />);
    fireEvent.click(await screen.findByRole("tab", { name: /Approvals/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Approve" }));
    await waitFor(() => expect(h.requestsApprove).toHaveBeenCalledWith("r1"));
  });
});

describe("Accounts", () => {
  it("lists accounts with memberships", async () => {
    renderWithProviders(<Accounts />);
    expect(await screen.findByText("eng@test")).toBeInTheDocument();
    expect(screen.getByText(/Engineer · A/)).toBeInTheDocument();
  });

  it("creates an account and reveals the password once", async () => {
    renderWithProviders(<Accounts />);
    fireEvent.change(await screen.findByPlaceholderText("name@company.com"), {
      target: { value: "new@test" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(h.usersCreate).toHaveBeenCalledWith("new@test", undefined));
    expect(await screen.findByText("pw")).toBeInTheDocument();
  });
});

describe("Pricing", () => {
  it("lists rates and searches", async () => {
    renderWithProviders(<PricingPage />);
    expect(await screen.findByText("gpt-4o-mini")).toBeInTheDocument();
    expect(screen.getByText("exact")).toBeInTheDocument();
  });

  it("adds a price", async () => {
    renderWithProviders(<PricingPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Add price" }));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByPlaceholderText("openai"), {
      target: { value: "anthropic" },
    });
    fireEvent.change(within(dialog).getByPlaceholderText("gpt-4o-mini"), {
      target: { value: "claude" },
    });
    fireEvent.change(within(dialog).getByPlaceholderText("0.15"), { target: { value: "3" } });
    fireEvent.change(within(dialog).getByPlaceholderText("0.60"), { target: { value: "15" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Add price" }));
    await waitFor(() =>
      expect(h.pricingCreate).toHaveBeenCalledWith(
        expect.objectContaining({ provider: "anthropic", model: "claude", input_price_per_1m: 3 })
      )
    );
  });

  it("maps delete 409 to the immutable-history message", async () => {
    h.pricingRemove.mockRejectedValue(new Error("409: referenced"));
    renderWithProviders(<PricingPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete price" }));
    expect(await screen.findByText(/add a newer effective-dated price/)).toBeInTheDocument();
  });
});

describe("Alerts", () => {
  it("shows the tabs and acks an alert", async () => {
    renderWithProviders(<AlertsPage />);
    expect(await screen.findByRole("tab", { name: /Rules/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Channels/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Ack" }));
    await waitFor(() =>
      expect(h.alertsUpdate).toHaveBeenCalledWith("a1", "acknowledged")
    );
  });

  it("renders rules for managers without channel management", async () => {
    h.me.mockResolvedValue(profile(["manager"]));
    renderWithProviders(<AlertsPage />);
    fireEvent.click(await screen.findByRole("tab", { name: /Rules/ }));
    expect((await screen.findAllByText("Error rate")).length).toBeGreaterThan(0);
    expect(screen.queryByRole("tab", { name: /Channels/ })).not.toBeInTheDocument();
  });
});

describe("Login", () => {
  it("submits credentials", async () => {
    // Signed out: /auth/me rejects so the form stays instead of redirecting.
    h.me.mockRejectedValue(new Error("401"));
    renderWithProviders(<Login />, { route: "/login" });
    fireEvent.change(await screen.findByLabelText("Email"), {
      target: { value: "a@b.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Sign in/ }));
    await waitFor(() => expect(h.login).toHaveBeenCalledWith("a@b.com", "secret"));
  });
});

describe("FilterToolbar", () => {
  it("writes day/client/workflow changes into the query", async () => {
    renderWithProviders(<Overview />);
    const range = await screen.findByLabelText("Time range in days");
    fireEvent.change(range, { target: { value: "7" } });
    await waitFor(() =>
      expect(h.overview).toHaveBeenLastCalledWith(expect.objectContaining({ days: 7 }))
    );

    fireEvent.change(screen.getByPlaceholderText("client id"), {
      target: { value: "client-42" },
    });
    await waitFor(() =>
      expect(h.overview).toHaveBeenLastCalledWith(
        expect.objectContaining({ client_id: "client-42" })
      )
    );

    fireEvent.change(screen.getByPlaceholderText("workflow"), {
      target: { value: "checkout" },
    });
    await waitFor(() =>
      expect(h.overview).toHaveBeenLastCalledWith(
        expect.objectContaining({ workflow: "checkout" })
      )
    );

    fireEvent.click(screen.getByRole("button", { name: /Clear/ }));
    await waitFor(() =>
      expect(h.overview).toHaveBeenLastCalledWith(
        expect.not.objectContaining({ client_id: "client-42" })
      )
    );
  });
});

describe("Manager budgets (edit/delete)", () => {
  it("edits and deletes a budget", async () => {
    renderWithProviders(<Manager />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByDisplayValue("Team cap"), {
      target: { value: "Renamed cap" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(h.budgetUpdate).toHaveBeenCalledWith(
        "b1",
        expect.objectContaining({ name: "Renamed cap" })
      )
    );

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(await screen.findByRole("button", { name: "Delete budget" }));
    await waitFor(() => expect(h.budgetRemove).toHaveBeenCalledWith("b1"));
  });
});

describe("Project key lifecycle", () => {
  const Routed = () => (
    <Routes>
      <Route path="/projects/:projectId" element={<Project />} />
    </Routes>
  );

  it("rotates and revokes a key", async () => {
    renderWithProviders(<Routed />, { route: "/projects/p1" });
    fireEvent.click(await screen.findByRole("button", { name: "Rotate" }));
    await waitFor(() => expect(h.keysRotate).toHaveBeenCalledWith("p1", "k1"));
    expect(await screen.findByText("rotated-key")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(await screen.findByRole("button", { name: "Delete key" }));
    await waitFor(() => expect(h.keysRevoke).toHaveBeenCalledWith("p1", "k1"));
  });
});

describe("Requests forms & rejection", () => {
  it("submits a department request", async () => {
    renderWithProviders(<Requests />);
    fireEvent.change(await screen.findByPlaceholderText("e.g. Data Platform"), {
      target: { value: "Analytics" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Submit request" }));
    await waitFor(() =>
      expect(h.requestsCreate).toHaveBeenCalledWith("create_department", { name: "Analytics" })
    );
  });

  it("requires a reason in the reject modal", async () => {
    renderWithProviders(<Requests />);
    fireEvent.click(await screen.findByRole("tab", { name: /Approvals/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Reject" }));
    const dialog = screen.getByRole("dialog");
    const confirm = within(dialog).getByRole("button", { name: "Confirm reject" });
    expect(confirm).toBeDisabled();
    fireEvent.change(within(dialog).getByPlaceholderText("Reason (required)"), {
      target: { value: "Not enough context" },
    });
    fireEvent.click(confirm);
    await waitFor(() =>
      expect(h.requestsReject).toHaveBeenCalledWith("r1", "Not enough context")
    );
  });
});

describe("Accounts memberships & password actions", () => {
  it("grants, revokes, resets and disables", async () => {
    renderWithProviders(<Accounts />);
    fireEvent.click(await screen.findByRole("button", { name: "Memberships" }));
    const dialog = screen.getByRole("dialog");

    const scope = within(dialog).getByLabelText("Membership scope");
    fireEvent.focus(scope);
    fireEvent.mouseDown(await screen.findByText("Team — A (Ops)"));
    fireEvent.click(within(dialog).getByRole("button", { name: "Grant membership" }));
    await waitFor(() => expect(h.usersGrant).toHaveBeenCalled());

    fireEvent.click(within(dialog).getByRole("button", { name: "Revoke" }));
    await waitFor(() => expect(h.usersRevoke).toHaveBeenCalledWith("u2", "m1"));

    fireEvent.click(screen.getByRole("button", { name: "Reset password" }));
    await waitFor(() => expect(h.usersReset).toHaveBeenCalledWith("u2"));
    fireEvent.click(screen.getByRole("button", { name: "Disable" }));
    await waitFor(() => expect(h.usersDisable).toHaveBeenCalledWith("u2"));
  });
});

describe("Alerts rules & channels management", () => {
  it("creates, edits and toggles rules; creates and deletes channels", async () => {
    renderWithProviders(<AlertsPage />);
    fireEvent.click(await screen.findByRole("tab", { name: /Rules/ }));

    fireEvent.click(await screen.findByRole("button", { name: "New rule" }));
    let dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByPlaceholderText("Team A error rate"), {
      target: { value: "My rule" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create rule" }));
    await waitFor(() =>
      expect(h.rulesCreate).toHaveBeenCalledWith(expect.objectContaining({ name: "My rule" }))
    );

    fireEvent.click(screen.getAllByRole("button", { name: "Edit" })[0]);
    dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Name"), {
      target: { value: "Error rate v2" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(h.rulesUpdate).toHaveBeenCalledWith(
        "rule-1",
        expect.objectContaining({ name: "Error rate v2" })
      )
    );

    fireEvent.click(screen.getByRole("button", { name: "Disable" }));
    await waitFor(() => expect(h.rulesUpdate).toHaveBeenCalledWith("rule-1", { enabled: false }));

    fireEvent.click(screen.getByRole("tab", { name: /Channels/ }));
    fireEvent.click(await screen.findByRole("button", { name: "New channel" }));
    dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByPlaceholderText("Ops email"), {
      target: { value: "Slack ops" },
    });
    fireEvent.change(within(dialog).getByPlaceholderText("https://hooks.slack.com/…"), {
      target: { value: "https://hooks.test/x" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create channel" }));
    await waitFor(() =>
      expect(h.channelsCreate).toHaveBeenCalledWith(
        expect.objectContaining({ name: "Slack ops", target: "https://hooks.test/x" })
      )
    );

    fireEvent.click(screen.getAllByRole("button", { name: "Delete" })[0]);
    fireEvent.click(await screen.findByRole("button", { name: "Delete channel" }));
    await waitFor(() => expect(h.channelsRemove).toHaveBeenCalledWith("ch1"));
  });
});

describe("Client drill-down", () => {
  it("filters errors by workflow and clears the drill-down", async () => {
    h.me.mockResolvedValue(profile(["client"]));
    h.executions.mockImplementation(
      (_f: unknown, opts?: { status?: string }) =>
        Promise.resolve(
          opts?.status === "error"
            ? {
                items: [{ ...execution, status: "error", error_kind: "rate_limit" }],
                total: 1,
              }
            : { items: [execution], total: 1 }
        )
    );
    renderWithProviders(<Client />);
    fireEvent.click((await screen.findAllByText("checkout"))[0]);
    expect(await screen.findByText("rate_limit")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(await screen.findByText("No workflow selected")).toBeInTheDocument();
  });
});

describe("ExecutionDetail failure tree & metadata", () => {
  const Routed = () => (
    <Routes>
      <Route path="/engineering/:id" element={<ExecutionDetail />} />
    </Routes>
  );

  it("renders the failure tree and business context tabs", async () => {
    h.failures.mockResolvedValue({
      execution_id: "e1",
      error_count: 1,
      nodes: [
        {
          span_id: "s1",
          parent_id: null,
          kind: "TOOL",
          name: "lookup_order",
          status: "error",
          error_kind: "tool_error",
          error_type: "Timeout",
          error_message: "timed out",
          started_at: "2026-10-01T10:00:00Z",
        },
      ],
    });
    renderWithProviders(<Routed />, { route: "/engineering/e1" });
    fireEvent.click(await screen.findByRole("tab", { name: /Failures/ }));
    expect(await screen.findByText("tool_error")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /Business context/ }));
    expect(await screen.findByText(/channel/)).toBeInTheDocument();
  });

  it("renders the span explorer when spans exist", async () => {
    h.spans.mockResolvedValue({
      items: [
        {
          id: "s1",
          span_id: "s1",
          parent_id: null,
          kind: "CHAIN",
          name: "checkout",
          status: "ok",
          error_type: null,
          error_message: null,
          error_kind: null,
          started_at: "2026-10-01T10:00:00Z",
          ended_at: "2026-10-01T10:00:02Z",
          duration_ms: 2000,
          llm_model: null,
          llm_provider: null,
          input_tokens: 0,
          output_tokens: 0,
          total_tokens: 0,
          tool_name: null,
          retrieval_doc_count: null,
          retry_count: 0,
          cost: null,
          attributes: {},
        },
        {
          id: "s2",
          span_id: "s2",
          parent_id: "s1",
          kind: "LLM",
          name: "llm_call",
          status: "ok",
          error_type: null,
          error_message: null,
          error_kind: null,
          started_at: "2026-10-01T10:00:00Z",
          ended_at: "2026-10-01T10:00:01Z",
          duration_ms: 1000,
          llm_model: "gpt-4o-mini",
          llm_provider: "openai",
          input_tokens: 100,
          output_tokens: 50,
          total_tokens: 150,
          tool_name: null,
          retrieval_doc_count: null,
          retry_count: 0,
          cost: 0.001,
          attributes: {},
        },
      ],
      total: 2,
    });
    renderWithProviders(<Routed />, { route: "/engineering/e1" });
    expect(await screen.findByRole("tab", { name: /Spans/ })).toBeInTheDocument();
    expect((await screen.findAllByText(/checkout|llm_call/)).length).toBeGreaterThan(0);
  });
});

describe("BudgetDialog scope pickers", () => {
  it("links department, team and project selects", async () => {
    h.me.mockResolvedValue(profile(["manager"]));
    renderWithProviders(<Manager />);
    fireEvent.click(await screen.findByRole("button", { name: "New budget" }));
    const dialog = screen.getByRole("dialog");

    const department = within(dialog).getByLabelText("Budget department");
    fireEvent.focus(department);
    fireEvent.mouseDown(await within(dialog).findByText("Ops"));

    const team = within(dialog).getByLabelText("Budget team");
    expect(team).not.toBeDisabled();
    fireEvent.focus(team);
    fireEvent.mouseDown(await within(dialog).findByText("A (Ops)"));

    const project = within(dialog).getByLabelText("Budget project");
    fireEvent.focus(project);
    fireEvent.mouseDown(await within(dialog).findByText("p1 · Checkout"));

    fireEvent.change(within(dialog).getByPlaceholderText("100"), { target: { value: "25" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create budget" }));
    await waitFor(() =>
      expect(h.budgetCreate).toHaveBeenCalledWith(
        expect.objectContaining({ department: "d1", team: "t1", project: "p1" })
      )
    );
  });
});
