import { useState, type ReactElement } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useAlerts } from "../api/hooks";
import { useRole, type Role } from "../state/RoleContext";
import { useTheme } from "../state/ThemeContext";
import { Select } from "./core";
import {
  IconAlertTriangle,
  IconChart,
  IconChevronRight,
  IconCoins,
  IconDashboard,
  IconMoon,
  IconPanelLeft,
  IconSparkle,
  IconSun,
  IconTrace,
} from "./core/icons";

interface NavItem {
  to: string;
  label: string;
  icon: (p: { size?: number }) => ReactElement;
  allow: Role[];
  end?: boolean;
}

const NAV_ITEMS: (NavItem | "separator")[] = [
  {
    to: "/",
    label: "Overview",
    icon: IconDashboard,
    allow: ["all", "engineer", "manager", "executive"],
    end: true,
  },
  { to: "/engineering", label: "Engineering", icon: IconTrace, allow: ["all", "engineer"] },
  "separator",
  { to: "/manager", label: "Manager", icon: IconChart, allow: ["all", "manager"] },
  { to: "/executive", label: "Executive", icon: IconCoins, allow: ["all", "executive"] },
];

const ROUTE_TITLES: { prefix: string; label: string }[] = [
  { prefix: "/engineering/", label: "Execution" },
  { prefix: "/engineering", label: "Engineering" },
  { prefix: "/manager", label: "Manager" },
  { prefix: "/executive", label: "Executive" },
  { prefix: "/", label: "Overview" },
];

function useBreadcrumbs(): string[] {
  const { pathname } = useLocation();
  const current = ROUTE_TITLES.find(
    (r) => pathname === r.prefix || pathname.startsWith(r.prefix)
  );
  if (!current) return ["Overview"];
  if (current.prefix === "/engineering/" && pathname.startsWith("/engineering/")) {
    return ["Engineering", "Execution"];
  }
  return [current.label];
}

const SIDEBAR_KEY = "aiobs.sidebar";

export function AppShell() {
  const { role } = useRole();
  const { data } = useAlerts();
  const openAlerts = data?.total ?? 0;
  const [expanded, setExpanded] = useState<boolean>(
    () => (typeof localStorage !== "undefined" ? localStorage.getItem(SIDEBAR_KEY) !== "collapsed" : true)
  );
  const breadcrumbs = useBreadcrumbs();

  const toggleSidebar = () => {
    setExpanded((prev) => {
      localStorage.setItem(SIDEBAR_KEY, prev ? "collapsed" : "expanded");
      return !prev;
    });
  };

  return (
    <div className="app">
      <SideNav expanded={expanded} openAlerts={openAlerts} role={role} />
      <div className="app__main">
        <TopNav
          breadcrumbs={breadcrumbs}
          openAlerts={openAlerts}
          sidebarExpanded={expanded}
          onToggleSidebar={toggleSidebar}
        />
        <div className="app__content">
          <Outlet />
        </div>
      </div>
    </div>
  );
}

function SideNav({
  expanded,
  openAlerts,
  role,
}: {
  expanded: boolean;
  openAlerts: number;
  role: Role;
}) {
  const { theme, setTheme } = useTheme();
  return (
    <nav className="side-nav" data-expanded={expanded} aria-label="Primary">
      <Link to="/" className="side-nav__brand" title="AI Observability Platform">
        <span className="side-nav__brand-mark">
          <IconSparkle size={22} />
        </span>
        <span className="side-nav__brand-text">AI Observability</span>
      </Link>
      <ul className="side-nav__nav">
        {NAV_ITEMS.map((item, i) =>
          item === "separator" ? (
            <li key={`sep-${i}`} className="nav-separator" role="presentation">
              <hr className="divider" />
            </li>
          ) : item.allow.includes(role) ? (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.end}
                className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
                title={expanded ? undefined : item.label}
              >
                <span className="nav-link__icon">
                  <item.icon size={18} />
                </span>
                <span className="nav-link__text">{item.label}</span>
                {item.to === "/manager" && openAlerts > 0 ? (
                  <span className="nav-link__counter">{openAlerts}</span>
                ) : null}
              </NavLink>
            </li>
          ) : null
        )}
      </ul>
      <div className="side-nav__footer">
        <button
          type="button"
          className="nav-link"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
        >
          <span className="nav-link__icon">
            {theme === "dark" ? <IconSun size={18} /> : <IconMoon size={18} />}
          </span>
          <span className="nav-link__text">
            {theme === "dark" ? "Light mode" : "Dark mode"}
          </span>
        </button>
      </div>
    </nav>
  );
}

function TopNav({
  breadcrumbs,
  openAlerts,
  sidebarExpanded,
  onToggleSidebar,
}: {
  breadcrumbs: string[];
  openAlerts: number;
  sidebarExpanded: boolean;
  onToggleSidebar: () => void;
}) {
  return (
    <header className="top-nav">
      <button
        type="button"
        className="button"
        data-variant="quiet"
        data-size="S"
        data-icon-only="true"
        onClick={onToggleSidebar}
        aria-label={sidebarExpanded ? "Collapse navigation" : "Expand navigation"}
        aria-expanded={sidebarExpanded}
        title={sidebarExpanded ? "Collapse navigation" : "Expand navigation"}
      >
        <IconPanelLeft size={16} />
      </button>
      <nav className="top-nav__breadcrumbs" aria-label="Breadcrumb">
        {breadcrumbs.map((crumb, i) => (
          <span key={crumb} className="row" style={{ gap: 4 }}>
            {i > 0 ? (
              <span className="top-nav__crumb-separator">
                <IconChevronRight size={12} />
              </span>
            ) : null}
            <span
              className={
                i === breadcrumbs.length - 1
                  ? "top-nav__crumb top-nav__crumb--current"
                  : "top-nav__crumb"
              }
            >
              {crumb}
            </span>
          </span>
        ))}
      </nav>
      <div className="top-nav__actions">
        <Link
          to="/manager"
          className="top-nav__alerts"
          data-open={openAlerts > 0}
          title={`${openAlerts} open alert${openAlerts === 1 ? "" : "s"}`}
        >
          <IconAlertTriangle size={14} />
          {openAlerts} open
        </Link>
        <RoleSwitcher />
      </div>
    </header>
  );
}

function RoleSwitcher() {
  const { role, setRole } = useRole();
  return (
    <Select
      value={role}
      onChange={(e) => setRole(e.target.value as Role)}
      aria-label="Persona"
      title="Restricts the visible views to a persona"
      style={{ minWidth: 130 }}
    >
      <option value="all">All views</option>
      <option value="engineer">Engineer</option>
      <option value="manager">SDM</option>
      <option value="executive">Finance</option>
    </Select>
  );
}
