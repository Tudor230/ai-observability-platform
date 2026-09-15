import { lazy, Suspense, type ReactNode } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { Skeleton } from "./components/core";
import { FiltersProvider } from "./state/FiltersContext";
import { RoleProvider, useRole, type Role } from "./state/RoleContext";
import { ThemeProvider } from "./state/ThemeContext";

const Overview = lazy(() => import("./pages/Overview"));
const Engineering = lazy(() => import("./pages/Engineering"));
const ExecutionDetail = lazy(() => import("./pages/ExecutionDetail"));
const Manager = lazy(() => import("./pages/Manager"));
const Executive = lazy(() => import("./pages/Executive"));

function Loading() {
  return (
    <div className="page">
      <Skeleton shape="title" width={220} />
      <div className="grid grid-4">
        <Skeleton shape="chart" />
        <Skeleton shape="chart" />
        <Skeleton shape="chart" />
        <Skeleton shape="chart" />
      </div>
    </div>
  );
}

function RequireRole({ allow, children }: { allow: Role[]; children: ReactNode }) {
  const { role } = useRole();
  if (!allow.includes(role)) return <Navigate to="/" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <ThemeProvider>
      <RoleProvider>
        <FiltersProvider>
          <Suspense fallback={<Loading />}>
            <Routes>
              <Route element={<AppShell />}>
                <Route index element={<Overview />} />
                <Route
                  path="engineering"
                  element={
                    <RequireRole allow={["all", "engineer"]}>
                      <Engineering />
                    </RequireRole>
                  }
                />
                <Route
                  path="engineering/:id"
                  element={
                    <RequireRole allow={["all", "engineer"]}>
                      <ExecutionDetail />
                    </RequireRole>
                  }
                />
                <Route
                  path="manager"
                  element={
                    <RequireRole allow={["all", "manager"]}>
                      <Manager />
                    </RequireRole>
                  }
                />
                <Route
                  path="executive"
                  element={
                    <RequireRole allow={["all", "executive"]}>
                      <Executive />
                    </RequireRole>
                  }
                />
              </Route>
            </Routes>
          </Suspense>
        </FiltersProvider>
      </RoleProvider>
    </ThemeProvider>
  );
}
