import { useEffect, useRef, useState, type ReactElement } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useAlerts, usePendingApprovals } from "../api/hooks";
import { useAuth } from "../state/AuthContext";
import { useTheme } from "../state/ThemeContext";
import { Button } from "./core";
import {
  IconAlertTriangle,
  IconChart,
  IconChevronDown,
  IconChevronRight,
  IconCoins,
  IconDashboard,
  IconInbox,
  IconLayers,
  IconLogOut,
  IconMoon,
  IconPanelLeft,
  IconSparkle,
  IconSun,
  IconTrace,
  IconUserCog,
  IconUsers,
} from "./core/icons";
import type { Role } from "../api/types";

interface NavItem {
  to: string;
  label: string;
  icon: (p: { size?: number }) => ReactElement;
  allow: Role[];
  end?: boolean;
}

const ALL_ROLES: Role[] = ["admin", "exec", "manager", "engineer", "client"];

const NAV_ITEMS: (NavItem | "separator")[] = [
  { to: "/", label: "Overview", icon: IconDashboard, allow: ALL_ROLES, end: true },
  { to: "/engineering", label: "Engineering", icon: IconTrace, allow: ["engineer", "manager"] },
  { to: "/manager", label: "Manager", icon: IconChart, allow: ["manager", "exec"] },
  { to: "/executive", label: "Executive", icon: IconCoins, allow: ["exec"] },
  { to: "/client", label: "Client", icon: IconUsers, allow: ["client"] },
  "separator",
  { to: "/projects", label: "Projects", icon: IconLayers, allow: ALL_ROLES },
  { to: "/requests", label: "Requests", icon: IconInbox, allow: ALL_ROLES },
  "separator",
  { to: "/accounts", label: "Accounts", icon: IconUserCog, allow: ["admin"] },
];

const ROUTE_TITLES: { prefix: string; label: string }[] = [
  { prefix: "/engineering/", label: "Execution" },
  { prefix: "/engineering", label: "Engineering" },
  { prefix: "/manager", label: "Manager" },
  { prefix: "/executive", label: "Executive" },
  { prefix: "/client", label: "Client" },
  { prefix: "/projects/", label: "Project" },
  { prefix: "/projects", label: "Projects" },
  { prefix: "/requests", label: "Requests" },
  { prefix: "/accounts", label: "Accounts" },
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
  if (current.prefix === "/projects/" && pathname.startsWith("/projects/")) {
    return ["Projects", "Project"];
  }
  return [current.label];
}

const SIDEBAR_KEY = "aiobs.sidebar";

export function AppShell() {
  const { hasRole, canApprove } = useAuth();
  const canSeeAlerts = hasRole("manager", "exec");
  const { data: alerts } = useAlerts(canSeeAlerts);
  const openAlerts = alerts?.total ?? 0;
  const { data: approvals } = usePendingApprovals(canApprove);
  const pendingApprovals = approvals?.pending_approvals ?? 0;
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
      <SideNav
        expanded={expanded}
        openAlerts={openAlerts}
        canSeeAlerts={canSeeAlerts}
        pendingApprovals={pendingApprovals}
        hasRole={hasRole}
      />
      <div className="app__main">
        <TopNav
          breadcrumbs={breadcrumbs}
          openAlerts={openAlerts}
          canSeeAlerts={canSeeAlerts}
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
  canSeeAlerts,
  pendingApprovals,
  hasRole,
}: {
  expanded: boolean;
  openAlerts: number;
  canSeeAlerts: boolean;
  pendingApprovals: number;
  hasRole: (...allowed: Role[]) => boolean;
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
          ) : hasRole(...item.allow) ? (
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
                {item.to === "/manager" && canSeeAlerts && openAlerts > 0 ? (
                  <span className="nav-link__counter">{openAlerts}</span>
                ) : null}
                {item.to === "/requests" && pendingApprovals > 0 ? (
                  <span className="nav-link__counter">{pendingApprovals}</span>
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
  canSeeAlerts,
  sidebarExpanded,
  onToggleSidebar,
}: {
  breadcrumbs: string[];
  openAlerts: number;
  canSeeAlerts: boolean;
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
        {canSeeAlerts ? (
          <Link
            to="/manager"
            className="top-nav__alerts"
            data-open={openAlerts > 0}
            title={`${openAlerts} open alert${openAlerts === 1 ? "" : "s"}`}
          >
            <IconAlertTriangle size={14} />
            {openAlerts} open
          </Link>
        ) : null}
        <UserMenu />
      </div>
    </header>
  );
}

function UserMenu() {
  const { profile, roles, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  if (!profile) return null;
  const roleList = Array.from(roles).filter((role) => role !== "admin");

  return (
    <div className="user-menu" ref={ref}>
      <Button
        variant="quiet"
        onClick={() => setOpen((prev) => !prev)}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <span className="user-menu__avatar">
          {profile.user.email.slice(0, 1).toUpperCase()}
        </span>
        <span className="user-menu__email">{profile.user.email}</span>
        <IconChevronDown size={12} />
      </Button>
      {open ? (
        <div className="user-menu__popover" role="menu">
          <div className="user-menu__meta">
            <div className="truncate">{profile.user.email}</div>
            <div className="muted">
              {roleList.length ? roleList.join(" · ") : "No memberships yet"}
            </div>
          </div>
          <button
            type="button"
            className="user-menu__item"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              void logout();
            }}
          >
            <IconLogOut size={14} />
            Log out
          </button>
        </div>
      ) : null}
    </div>
  );
}
