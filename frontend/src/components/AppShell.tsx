import { NavLink, Outlet } from "react-router-dom";
import { useFilters } from "../state/FiltersContext";
import { useAlerts } from "../api/hooks";

const links = [
  { to: "/", label: "Overview" },
  { to: "/engineering", label: "Engineering" },
  { to: "/manager", label: "Manager" },
  { to: "/executive", label: "Executive" },
];

export function AppShell() {
  const { filters, setFilters } = useFilters();
  const { data } = useAlerts();
  const open = data?.total ?? 0;

  return (
    <div className="shell">
      <header className="topbar">
        <span className="brand">AI Observability</span>
        <nav className="nav">
          {links.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.to === "/"}
              className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
            >
              {l.label}
            </NavLink>
          ))}
        </nav>
        <span className="alerts-badge" title="open alerts">
          ⚠ {open}
        </span>
      </header>

      <FilterBar filters={filters} onChange={setFilters} />

      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}

function FilterBar({
  filters,
  onChange,
}: {
  filters: { days: number; client_id?: string; workflow?: string };
  onChange: (f: typeof filters) => void;
}) {
  return (
    <div className="filterbar">
      <label>
        Days
        <select
          value={filters.days}
          onChange={(e) => onChange({ ...filters, days: Number(e.target.value) })}
        >
          {[7, 14, 30, 90].map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
      </label>
      <label>
        Client
        <input
          value={filters.client_id ?? ""}
          placeholder="client id"
          onChange={(e) => onChange({ ...filters, client_id: e.target.value || undefined })}
        />
      </label>
      <label>
        Workflow
        <input
          value={filters.workflow ?? ""}
          placeholder="workflow"
          onChange={(e) => onChange({ ...filters, workflow: e.target.value || undefined })}
        />
      </label>
    </div>
  );
}
