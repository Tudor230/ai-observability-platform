import type { ReactElement, ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import { AuthProvider } from "../state/AuthContext";
import { ThemeProvider } from "../state/ThemeContext";

interface Options {
  /** Initial router entry, e.g. `/manager`. */
  route?: string;
  /** Skip AuthProvider when the test renders its own auth mock. */
  withAuth?: boolean;
}

/**
 * Render a component/page with the app's providers and a fresh QueryClient.
 * Tests mock `../api/client` (vi.mock) to control data; retries are off so
 * failures surface immediately.
 */
export function renderWithProviders(
  ui: ReactElement,
  { route = "/", withAuth = true }: Options = {}
): RenderResult {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 }, mutations: { retry: false } },
  });

  const withRouter = (children: ReactNode) => (
    <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
  );

  return render(
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        {withAuth ? withRouter(<AuthProvider>{ui}</AuthProvider>) : withRouter(ui)}
      </QueryClientProvider>
    </ThemeProvider>
  );
}

/** A minimal profile builder for auth-dependent tests. */
export function profile(
  roles: string[],
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    user: { id: "u1", email: "user@test", enabled: true, created_at: null },
    roles,
    can_approve: roles.some((r) => r === "admin" || r === "exec" || r === "manager"),
    memberships: [],
    ...overrides,
  };
}
