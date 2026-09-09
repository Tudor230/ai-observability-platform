import { lazy, Suspense } from "react";
import { Routes, Route } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { FiltersProvider } from "./state/FiltersContext";

const Overview = lazy(() => import("./pages/Overview"));
const Engineering = lazy(() => import("./pages/Engineering"));
const ExecutionDetail = lazy(() => import("./pages/ExecutionDetail"));
const Manager = lazy(() => import("./pages/Manager"));
const Executive = lazy(() => import("./pages/Executive"));

function Loading() {
  return <p className="muted">Loading…</p>;
}

export default function App() {
  return (
    <FiltersProvider>
      <Suspense fallback={<Loading />}>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<Overview />} />
            <Route path="engineering" element={<Engineering />} />
            <Route path="engineering/:id" element={<ExecutionDetail />} />
            <Route path="manager" element={<Manager />} />
            <Route path="executive" element={<Executive />} />
          </Route>
        </Routes>
      </Suspense>
    </FiltersProvider>
  );
}