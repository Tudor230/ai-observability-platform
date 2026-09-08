import { Routes, Route } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { FiltersProvider } from "./state/FiltersContext";
import Overview from "./pages/Overview";
import Engineering from "./pages/Engineering";
import ExecutionDetail from "./pages/ExecutionDetail";
import Manager from "./pages/Manager";
import Executive from "./pages/Executive";

export default function App() {
  return (
    <FiltersProvider>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<Overview />} />
          <Route path="engineering" element={<Engineering />} />
          <Route path="engineering/:id" element={<ExecutionDetail />} />
          <Route path="manager" element={<Manager />} />
          <Route path="executive" element={<Executive />} />
        </Route>
      </Routes>
    </FiltersProvider>
  );
}
