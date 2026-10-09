import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";

const h = vi.hoisted(() => ({
  me: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  overview: vi.fn(),
  metrics: vi.fn(),
  alerts: vi.fn(),
}));

vi.mock("./api/client", () => ({
  ApiError: class ApiError extends Error {},
  setUnauthorizedHandler: vi.fn(),
  api: {
    auth: { me: h.me, login: h.login, logout: h.logout },
    overview: h.overview,
    metrics: h.metrics,
    alerts: { list: h.alerts, update: vi.fn() },
    requests: { list: vi.fn().mockResolvedValue({ items: [], total: 0, pending_approvals: 0 }) },
    directory: { projects: vi.fn().mockResolvedValue({ items: [], total: 0 }) },
  },
}));

function profile(roles: string[]) {
  return {
    user: { id: "u1", email: "user@test", enabled: true, created_at: null },
    roles,
    memberships: [],
    can_approve: true,
  };
}

beforeEach(() => {
  h.me.mockReset();
  h.logout.mockReset();
  h.overview.mockReset().mockResolvedValue({
    executions: 0,
    failed_executions: 0,
    error_rate: 0,
    total_cost: 0,
    total_tokens: 0,
    llm_calls: 0,
    tool_calls: 0,
    avg_duration_ms: 0,
    p50_duration_ms: 0,
    p95_duration_ms: 0,
    p99_duration_ms: 0,
    deltas: { total_cost_pct: null, executions_pct: null, error_rate_pct: null },
    open_alerts: 0,
  });
  h.metrics.mockReset().mockResolvedValue({ items: [], total: 0 });
  h.alerts.mockReset().mockResolvedValue({ items: [], total: 0 });
});

function renderApp(entry: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[entry]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("App routing", () => {
  it("redirects unauthenticated visitors to the login screen", async () => {
    h.me.mockRejectedValue(new Error("401"));
    renderApp("/engineering");
    expect(await screen.findByText(/Sign in with your platform account/)).toBeInTheDocument();
  });

  it("redirects a disallowed role away from a guarded route", async () => {
    h.me.mockResolvedValue(profile(["engineer"]));
    renderApp("/executive");
    // Guarded route falls back to Overview instead of rendering Executive.
    expect(
      await screen.findByText(
        "Usage, cost and reliability across every agent execution.",
        {},
        { timeout: 5000 }
      )
    ).toBeInTheDocument();
    expect(
      screen.queryByText(
        "Unit economics of agentic AI — total spend, cost per execution and forecast."
      )
    ).not.toBeInTheDocument();
  });

  it("shows admin-only nav entries for admins and hides them for engineers", async () => {
    h.me.mockResolvedValue(profile(["admin"]));
    const { unmount } = renderApp("/");
    expect(await screen.findByRole("link", { name: /Pricing/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Accounts/ })).toBeInTheDocument();
    unmount();

    h.me.mockResolvedValue(profile(["engineer"]));
    renderApp("/");
    expect(await screen.findByRole("link", { name: /Engineering/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Pricing/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Accounts/ })).not.toBeInTheDocument();
  });

  it("collapses the sidebar, toggles the theme and logs out", async () => {
    h.me.mockResolvedValue(profile(["admin"]));
    renderApp("/");
    const collapse = await screen.findByLabelText("Collapse navigation");
    fireEvent.click(collapse);
    expect(await screen.findByLabelText("Expand navigation")).toBeInTheDocument();

    fireEvent.click(screen.getByTitle("Switch to light mode"));
    expect(await screen.findByTitle("Switch to dark mode")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /user@test/ }));
    fireEvent.click(await screen.findByRole("menuitem", { name: /Log out/ }));
    await waitFor(() => expect(h.logout).toHaveBeenCalled());
  });

  it("changes the auto-refresh cadence and refreshes manually", async () => {
    localStorage.clear();
    h.me.mockResolvedValue(profile(["admin"]));
    renderApp("/");
    const interval = await screen.findByLabelText("Auto-refresh interval");
    fireEvent.change(interval, { target: { value: "60000" } });
    expect(localStorage.getItem("aiobs.refresh")).toBe("60000");

    fireEvent.click(screen.getByRole("button", { name: /Refresh/ }));
    await waitFor(() => expect(h.overview.mock.calls.length).toBeGreaterThan(1));
  });
});
