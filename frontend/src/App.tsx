import { lazy, Suspense, type ReactNode } from "react";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { Skeleton } from "./components/core";
import type { Role } from "./api/types";
import { AuthProvider, useAuth } from "./state/AuthContext";
import { FiltersProvider } from "./state/FiltersContext";
import { ThemeProvider } from "./state/ThemeContext";

const Overview = lazy(() => import("./pages/Overview"));
const Engineering = lazy(() => import("./pages/Engineering"));
const ExecutionDetail = lazy(() => import("./pages/ExecutionDetail"));
const Manager = lazy(() => import("./pages/Manager"));
const Executive = lazy(() => import("./pages/Executive"));
const Client = lazy(() => import("./pages/Client"));
const Projects = lazy(() => import("./pages/Projects"));
const Requests = lazy(() => import("./pages/Requests"));
const Project = lazy(() => import("./pages/Project"));
const Accounts = lazy(() => import("./pages/Accounts"));
const Pricing = lazy(() => import("./pages/Pricing"));
const Alerts = lazy(() => import("./pages/Alerts"));
const Login = lazy(() => import("./pages/Login"));

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

function Splash() {
  return (
    <div className="login">
      <div className="login__card">
        <Skeleton shape="title" width={180} />
        <Skeleton shape="chart" />
      </div>
    </div>
  );
}

function RequireAuth({ children }: { children: ReactNode }) {
  const { profile, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Splash />;
  if (!profile) {
    return (
      <Navigate
        to="/login"
        state={{ from: location.pathname + location.search }}
        replace
      />
    );
  }
  return <>{children}</>;
}

function RequireRoles({ allow, children }: { allow: Role[]; children: ReactNode }) {
  const { hasRole } = useAuth();
  if (!hasRole(...allow)) return <Navigate to="/" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <FiltersProvider>
          <Suspense fallback={<Loading />}>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route
                element={
                  <RequireAuth>
                    <AppShell />
                  </RequireAuth>
                }
              >
                <Route index element={<Overview />} />
                <Route
                  path="engineering"
                  element={
                    <RequireRoles allow={["engineer", "manager"]}>
                      <Engineering />
                    </RequireRoles>
                  }
                />
                <Route
                  path="engineering/:id"
                  element={
                    <RequireRoles allow={["engineer", "manager", "client"]}>
                      <ExecutionDetail />
                    </RequireRoles>
                  }
                />
                <Route
                  path="manager"
                  element={
                    <RequireRoles allow={["manager", "exec"]}>
                      <Manager />
                    </RequireRoles>
                  }
                />
                <Route
                  path="executive"
                  element={
                    <RequireRoles allow={["exec"]}>
                      <Executive />
                    </RequireRoles>
                  }
                />
                <Route
                  path="client"
                  element={
                    <RequireRoles allow={["client"]}>
                      <Client />
                    </RequireRoles>
                  }
                />
                <Route path="requests" element={<Requests />} />
                <Route path="alerts" element={<Alerts />} />
                <Route path="projects" element={<Projects />} />
                <Route path="projects/:projectId" element={<Project />} />
                <Route
                  path="pricing"
                  element={
                    <RequireRoles allow={["admin"]}>
                      <Pricing />
                    </RequireRoles>
                  }
                />
                <Route
                  path="accounts"
                  element={
                    <RequireRoles allow={["admin"]}>
                      <Accounts />
                    </RequireRoles>
                  }
                />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Route>
            </Routes>
          </Suspense>
        </FiltersProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}
