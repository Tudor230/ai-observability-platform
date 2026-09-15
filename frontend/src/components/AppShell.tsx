import { NavLink, Outlet } from "react-router-dom";
import { useFilters } from "../state/FiltersContext";
import { useRole, type Role } from "../state/RoleContext";
import { useAlerts } from "../api/hooks";

const links: { to: string; label: string; allow: Role[] }[] = [
  { to: "/", label: "Overview", allow: ["all", "engineer", "manager", "executive"] },
  { to: "/engineering", label: "Engineering", allow: ["all", "engineer"] },
  { to: "/manager", label: "Manager", allow: ["all", "manager"] },
  { to: "/executive", label: "Executive", allow: ["all", "executive"] },
];

export function AppShell() {
  const { filters, setFilters } = useFilters();
  const { role } = useRole();
  const { data } = useAlerts();
  const open = data?.total ?? 0;

  return (
    <div className="shell">
      <header className="topbar">
        <span className="brand">AI Observability</span>
        <nav className="nav">
          {links
            .filter((l) => l.allow.includes(role))
            .map((l) => (
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
        <RoleSwitcher />
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

function RoleSwitcher() {
  const { role, setRole } = useRole();
  return (
    <label className="roles" title="Restricts the visible views to a persona">
      <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
        <option value="all">All views</option>
        <option value="engineer">Engineer</option>
        <option value="manager">SDM</option>
        <option value="executive">Finance</option>
      </select>
    </label>
  );
}

function FilterBar({
  filters,
  onChange,
}: {
  filters: { days: number; project_id?: string; client_id?: string; workflow?: string };
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
        Project
        <input
          value={filters.project_id ?? ""}
          placeholder="project id"
          onChange={(e) => onChange({ ...filters, project_id: e.target.value || undefined })}
        />
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
