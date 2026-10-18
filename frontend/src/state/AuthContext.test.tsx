import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, useAuth } from "./AuthContext";

const mocks = vi.hoisted(() => ({
  me: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  setUnauthorizedHandler: vi.fn(),
}));

vi.mock("../api/client", () => ({
  api: {
    auth: {
      me: mocks.me,
      login: mocks.login,
      logout: mocks.logout,
    },
  },
  setUnauthorizedHandler: mocks.setUnauthorizedHandler,
}));

function probeProfile(roles: string[]) {
  return {
    user: { id: "u1", email: "user@test", enabled: true, created_at: null },
    roles,
    memberships: [],
    can_approve: roles.some((r) => ["admin", "exec", "manager"].includes(r)),
  };
}

function Probe() {
  const { loading, profile, roles, costVisible, canApprove, hasRole, login, logout } = useAuth();
  return (
    <div>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="email">{profile?.user.email ?? "-"}</span>
      <span data-testid="roles">{[...roles].join(",")}</span>
      <span data-testid="cost">{String(costVisible)}</span>
      <span data-testid="approve">{String(canApprove)}</span>
      <span data-testid="exec">{String(hasRole("exec"))}</span>
      <span data-testid="admin">{String(hasRole("admin"))}</span>
      <button onClick={() => void login("a@b", "pw")}>login</button>
      <button onClick={() => void logout()}>logout</button>
    </div>
  );
}

function renderAuth() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <Probe />
      </AuthProvider>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  mocks.me.mockReset();
  mocks.login.mockReset();
  mocks.logout.mockReset();
  mocks.setUnauthorizedHandler.mockReset();
});

describe("AuthProvider", () => {
  it("loads the profile and derives roles and visibility", async () => {
    mocks.me.mockResolvedValue(probeProfile(["manager", "exec"]));
    renderAuth();
    await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("false"));
    expect(screen.getByTestId("email")).toHaveTextContent("user@test");
    expect(screen.getByTestId("roles")).toHaveTextContent("manager,exec");
    expect(screen.getByTestId("cost")).toHaveTextContent("true");
    expect(screen.getByTestId("approve")).toHaveTextContent("true");
    expect(screen.getByTestId("exec")).toHaveTextContent("true");
    expect(screen.getByTestId("admin")).toHaveTextContent("false");
    expect(mocks.setUnauthorizedHandler).toHaveBeenCalled();
  });

  it("grants admins every role", async () => {
    mocks.me.mockResolvedValue(probeProfile(["admin"]));
    renderAuth();
    await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("false"));
    expect(screen.getByTestId("exec")).toHaveTextContent("true");
    expect(screen.getByTestId("admin")).toHaveTextContent("true");
    expect(screen.getByTestId("cost")).toHaveTextContent("true");
  });

  it("hides cost data for the client role", async () => {
    mocks.me.mockResolvedValue(probeProfile(["client"]));
    renderAuth();
    await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("false"));
    expect(screen.getByTestId("cost")).toHaveTextContent("false");
  });

  it("treats a failed /auth/me as signed out", async () => {
    mocks.me.mockRejectedValue(new Error("401"));
    renderAuth();
    await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("false"));
    expect(screen.getByTestId("email")).toHaveTextContent("-");
  });

  it("logs in (profile replaced) and out (profile cleared)", async () => {
    mocks.me.mockResolvedValue(probeProfile(["engineer"]));
    mocks.login.mockResolvedValue(probeProfile(["admin"]));
    renderAuth();
    await waitFor(() => expect(screen.getByTestId("email")).toHaveTextContent("user@test"));

    fireEvent.click(screen.getByText("login"));
    await waitFor(() => expect(screen.getByTestId("roles")).toHaveTextContent("admin"));

    fireEvent.click(screen.getByText("logout"));
    await waitFor(() => expect(screen.getByTestId("email")).toHaveTextContent("-"));
    expect(mocks.logout).toHaveBeenCalled();
  });
});
