import { useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import {
  useDepartments,
  useDirectoryProjects,
  useRequests,
  useTeams,
} from "../api/hooks";
import type {
  AccessRequest,
  RequestStatus,
  RequestType,
  Role,
} from "../api/types";
import { PageHeader } from "../components/PageHeader";
import {
  Alert,
  Badge,
  Button,
  CardPanel,
  Dialog,
  EmptyState,
  Field,
  QueryError,
  SearchableSelect,
  Select,
  Skeleton,
  Table,
  TableEmpty,
  TableWrap,
  Tabs,
  Td,
  Textarea,
  TextInput,
  Th,
  Tr,
  useToast,
  type BadgeVariant,
} from "../components/core";
import { useAuth } from "../state/AuthContext";

type TabId = "new" | "approvals" | "mine";

const REQUEST_TYPES: { id: RequestType; label: string; title: string }[] = [
  { id: "create_department", label: "Department", title: "Register department" },
  { id: "create_team", label: "Team", title: "Register team" },
  { id: "create_project", label: "Project", title: "Register project" },
  { id: "membership", label: "Membership", title: "Request membership" },
];

const REQUESTABLE_ROLES: Role[] = ["engineer", "manager", "client"];

const ROLE_LABELS: Record<Role, string> = {
  admin: "Admin",
  exec: "Executive",
  manager: "Manager",
  engineer: "Engineer",
  client: "Client",
};

const STATUS_VARIANTS: Record<RequestStatus, BadgeVariant> = {
  pending: "warning",
  approved: "success",
  rejected: "danger",
  cancelled: "default",
};

function timeAgo(value: string | null): string {
  if (!value) return "—";
  const ms = Date.now() - new Date(value).getTime();
  const minutes = Math.round(ms / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.round(hours / 24)}d`;
}

function StatusBadge({ status }: { status: RequestStatus }) {
  return <Badge variant={STATUS_VARIANTS[status]}>{status}</Badge>;
}

export default function Requests() {
  const queryClient = useQueryClient();
  const { hasRole, canApprove, profile, refresh } = useAuth();
  const toast = useToast();
  const canRequestDepartments = hasRole("admin", "exec", "manager");
  const [tab, setTab] = useState<TabId>("new");

  const departments = useDepartments();
  const teams = useTeams();
  const projects = useDirectoryProjects();
  const approvals = useRequests("to_approve", canApprove);
  const mine = useRequests("mine");

  const visibleTypes = useMemo(
    () =>
      REQUEST_TYPES.filter(
        (option) => option.id !== "create_department" || canRequestDepartments
      ),
    [canRequestDepartments]
  );
  const visibleTabs = useMemo(
    () =>
      [
        { id: "new" as const, label: "New request" },
        ...(canApprove
          ? [
              {
                id: "approvals" as const,
                label: "Approvals",
                counter: approvals.data?.pending_approvals,
              },
            ]
          : []),
        { id: "mine" as const, label: "My requests" },
      ],
    [canApprove, approvals.data]
  );
  const activeTab = visibleTabs.some((item) => item.id === tab) ? tab : "new";

  const [type, setType] = useState<RequestType>("create_department");
  const [name, setName] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [teamId, setTeamId] = useState("");
  const [projectSlug, setProjectSlug] = useState("");
  const [projectName, setProjectName] = useState("");
  const [membershipRole, setMembershipRole] = useState<Role>("engineer");
  const [scopeKey, setScopeKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{ variant: "success" | "danger"; text: string } | null>(null);

  const [rejecting, setRejecting] = useState<AccessRequest | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [decidingId, setDecidingId] = useState<string | null>(null);

  // Roles can make a request type invisible (e.g. engineers can't create
  // departments); fall back to the first visible type without an effect.
  const activeType = visibleTypes.some((option) => option.id === type)
    ? type
    : visibleTypes[0].id;

  const scopeNames = useMemo(() => {
    const map = new Map<string, string>();
    for (const d of departments.data?.items ?? []) map.set(`department:${d.id}`, d.name);
    for (const t of teams.data?.items ?? [])
      map.set(`team:${t.id}`, `${t.name} (${t.department_name})`);
    for (const p of projects.data?.items ?? [])
      map.set(`project:${p.id}`, `${p.project_id} · ${p.name}`);
    return map;
  }, [departments.data, teams.data, projects.data]);

  function summarize(req: AccessRequest): string {
    const p = req.payload as Record<string, string | undefined>;
    switch (req.type) {
      case "create_department":
        return `Create department “${p.name}”`;
      case "create_team":
        return `Create team “${p.name}”`;
      case "create_project":
        return `Create project “${p.project_id} / ${p.name}”`;
      case "membership":
        return `Join as ${ROLE_LABELS[(p.role as Role) ?? "engineer"]}`;
      default:
        return req.type;
    }
  }

  function scopeLabel(req: AccessRequest): string {
    const p = req.payload as Record<string, string | undefined>;
    if (req.type === "create_department") return "—";
    if (req.type === "create_team")
      return scopeNames.get(`department:${p.department_id}`) ?? "—";
    if (req.type === "create_project") return scopeNames.get(`team:${p.team_id}`) ?? "—";
    if (req.type === "membership")
      return p.scope_id
        ? scopeNames.get(`${p.scope_type}:${p.scope_id}`) ?? `${p.scope_type} ${p.scope_id}`
        : "Global";
    return "—";
  }

  function openProjectFor(req: AccessRequest): string | null {
    if (req.type !== "create_project" || req.status !== "approved") return null;
    const p = req.payload as Record<string, string | undefined>;
    return p.project_id ? `/projects/${p.project_id}` : null;
  }

  function invalidateRequests() {
    void queryClient.invalidateQueries({ queryKey: ["requests"] });
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (
      (activeType === "create_team" && !departmentId) ||
      (activeType === "create_project" && !teamId) ||
      (activeType === "membership" && !scopeKey)
    ) {
      setFeedback({ variant: "danger", text: "Select all required fields." });
      toast.error("Select all required fields.");
      return;
    }
    setBusy(true);
    setFeedback(null);
    let payload: Record<string, unknown>;
    if (activeType === "create_department") {
      payload = { name };
    } else if (activeType === "create_team") {
      payload = { name, department_id: departmentId };
    } else if (activeType === "create_project") {
      payload = { project_id: projectSlug, name: projectName, team_id: teamId };
    } else {
      const [scopeType, scopeId] = scopeKey.split(":");
      payload = {
        role: membershipRole,
        scope_type: scopeType,
        scope_id: scopeType === "global" ? null : scopeId,
      };
    }
    try {
      const result = await api.requests.create(activeType, payload);
      const text =
        result.status === "approved"
          ? activeType === "create_project"
            ? "Auto-approved (you cover this scope) — open the project to add an ingest key."
            : "Auto-approved: you cover this scope."
          : "Request submitted for approval.";
      setFeedback({ variant: "success", text });
      toast.success(text);
      setName("");
      setProjectSlug("");
      setProjectName("");
      setScopeKey("");
      invalidateRequests();
      if (result.status === "approved") void refresh();
    } catch (error) {
      const text = error instanceof Error ? error.message : "Request failed.";
      setFeedback({ variant: "danger", text });
      toast.error(text);
    } finally {
      setBusy(false);
    }
  }

  async function decide(
    req: AccessRequest,
    action: "approve" | "reject" | "cancel",
    reason?: string
  ) {
    setDecidingId(req.id);
    setFeedback(null);
    try {
      if (action === "approve") await api.requests.approve(req.id);
      else if (action === "reject") await api.requests.reject(req.id, reason ?? "");
      else await api.requests.cancel(req.id);
      toast.success(
        action === "approve"
          ? "Request approved."
          : action === "reject"
            ? "Request rejected."
            : "Request cancelled."
      );
      invalidateRequests();
      void queryClient.invalidateQueries({ queryKey: ["directory"] });
      void queryClient.invalidateQueries({ queryKey: ["overview"] });
    } catch (error) {
      const text = error instanceof Error ? error.message : "Action failed.";
      setFeedback({ variant: "danger", text });
      toast.error(text);
    } finally {
      setDecidingId(null);
      setRejecting(null);
      setRejectReason("");
    }
  }

  function resubmit(req: AccessRequest) {
    const p = req.payload as Record<string, string | undefined>;
    setType(req.type);
    setName(p.name ?? "");
    setDepartmentId(p.department_id ?? "");
    setTeamId(p.team_id ?? "");
    setProjectSlug(p.project_id ?? "");
    setProjectName(p.name ?? "");
    if (req.type === "membership") {
      setMembershipRole((p.role as Role) ?? "engineer");
      setScopeKey(p.scope_id ? `${p.scope_type}:${p.scope_id}` : "global:");
    }
    setFeedback(null);
    setTab("new");
  }

  // Grants the caller already holds (role+scope), so they aren't offered again.
  // A different role on the same scope stays requestable (e.g. engineer →
  // manager), matching the backend guard.
  const heldGrants = useMemo(() => {
    const grants = new Set<string>();
    for (const membership of profile?.memberships ?? []) {
      if (membership.status === "approved") {
        grants.add(
          `${membership.role}:${membership.scope_type}:${membership.scope_id ?? ""}`
        );
      }
    }
    return grants;
  }, [profile]);

  const scopeOptions = useMemo(() => {
    const holds = (scopeType: string, scopeId: string) =>
      heldGrants.has(`${membershipRole}:${scopeType}:${scopeId}`);
    if (membershipRole === "manager") {
      return [
        ...(departments.data?.items ?? [])
          .filter((d) => !holds("department", d.id))
          .map((d) => ({
            value: `department:${d.id}`,
            label: `Department — ${d.name}`,
          })),
        ...(teams.data?.items ?? [])
          .filter((t) => !holds("team", t.id))
          .map((t) => ({
            value: `team:${t.id}`,
            label: `Team — ${t.name} (${t.department_name})`,
          })),
      ];
    }
    if (membershipRole === "client") {
      return (projects.data?.items ?? [])
        .filter((p) => !holds("project", p.id))
        .map((p) => ({
          value: `project:${p.id}`,
          label: `Project — ${p.project_id} · ${p.name}`,
        }));
    }
    return (teams.data?.items ?? [])
      .filter((t) => !holds("team", t.id))
      .map((t) => ({
        value: `team:${t.id}`,
        label: `Team — ${t.name} (${t.department_name})`,
      }));
  }, [membershipRole, departments.data, teams.data, projects.data, heldGrants]);

  return (
    <div className="page">
      <PageHeader
        title="Requests"
        subTitle="Register an organisation unit or request a membership. Approvals route to the managers covering the scope."
      />

      <Tabs tabs={visibleTabs} selected={activeTab} onSelect={setTab}>
        {feedback ? <Alert variant={feedback.variant} message={feedback.text} /> : null}

        {activeTab === "new" ? (
          <>
            <div className="seg">
              {visibleTypes.map((option) => (
                <button
                  key={option.id}
                  type="button"
                  className="seg__btn"
                  data-active={option.id === activeType}
                  onClick={() => {
                    setType(option.id);
                    setFeedback(null);
                  }}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <CardPanel
              title={visibleTypes.find((t) => t.id === activeType)?.title}
              subTitle="An identical pending request is rejected as a duplicate."
            >
              <form className="request-form" onSubmit={submit}>
                {activeType === "create_department" ? (
                  <Field label="Department name">
                    <TextInput
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="e.g. Data Platform"
                      required
                    />
                  </Field>
                ) : null}

                {activeType === "create_team" ? (
                  <>
                    <Field label="Team name">
                      <TextInput
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        placeholder="e.g. Retrieval"
                        required
                      />
                    </Field>
                    <Field label="Department">
                      <SearchableSelect
                        value={departmentId}
                        onChange={setDepartmentId}
                        options={(departments.data?.items ?? []).map((d) => ({
                          value: d.id,
                          label: d.name,
                        }))}
                        placeholder="Select a department…"
                        aria-label="Department"
                      />
                    </Field>
                  </>
                ) : null}

                {activeType === "create_project" ? (
                  <>
                    <Field label="Project id (slug)">
                      <TextInput
                        value={projectSlug}
                        onChange={(e) => setProjectSlug(e.target.value)}
                        placeholder="e.g. proj-1"
                        required
                      />
                    </Field>
                    <Field label="Display name">
                      <TextInput
                        value={projectName}
                        onChange={(e) => setProjectName(e.target.value)}
                        placeholder="e.g. Demo Project"
                        required
                      />
                    </Field>
                    <Field label="Team">
                      <SearchableSelect
                        value={teamId}
                        onChange={setTeamId}
                        options={(teams.data?.items ?? []).map((t) => ({
                          value: t.id,
                          label: `${t.name} (${t.department_name})`,
                        }))}
                        placeholder="Select a team…"
                        aria-label="Team"
                      />
                    </Field>
                  </>
                ) : null}

                {activeType === "membership" ? (
                  <>
                    <Field label="Role">
                      <Select
                        value={membershipRole}
                        onChange={(e) => {
                          setMembershipRole(e.target.value as Role);
                          setScopeKey("");
                        }}
                      >
                        {REQUESTABLE_ROLES.map((role) => (
                          <option key={role} value={role}>
                            {ROLE_LABELS[role]}
                          </option>
                        ))}
                      </Select>
                    </Field>
                    <Field label="Scope">
                      <SearchableSelect
                        value={scopeKey}
                        onChange={setScopeKey}
                        options={scopeOptions}
                        placeholder="Select a scope…"
                        aria-label="Membership scope"
                      />
                    </Field>
                  </>
                ) : null}

                <div className="request-form__hint muted">
                  {activeType === "create_department"
                    ? "Admin/exec approve new departments; you become its initial manager."
                    : activeType === "membership"
                      ? `${
                          membershipRole === "manager"
                            ? "Manager grants are approved by admin/exec only."
                            : "A manager covering the scope approves this request."
                        } Scopes where you already hold this role are hidden.`
                      : "A manager covering the scope approves this request."}
                </div>
                <div className="row">
                  <Button variant="primary" type="submit" disabled={busy}>
                    {busy ? "Submitting…" : "Submit request"}
                  </Button>
                </div>
              </form>
            </CardPanel>
          </>
        ) : null}

        {activeTab === "approvals" ? (
          <CardPanel
            title="Pending approvals"
            subTitle="Requests your memberships cover"
          >
            {approvals.isError ? (
              <div style={{ padding: 16 }}>
                <QueryError what="approvals" error={approvals.error} />
              </div>
            ) : approvals.isLoading ? (
              <div className="stack" style={{ padding: 16 }}>
                <Skeleton width="60%" />
                <Skeleton width="80%" />
              </div>
            ) : approvals.data?.items.length ? (
              <TableWrap>
                <Table>
                  <thead>
                    <tr>
                      <Th>Type</Th>
                      <Th>Request</Th>
                      <Th>Requester</Th>
                      <Th>Scope</Th>
                      <Th>Age</Th>
                      <Th align="right">Actions</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {approvals.data.items.map((req) => (
                      <Tr key={req.id}>
                        <Td>
                          <span className="type-label">{req.type.replace("create_", "")}</span>
                        </Td>
                        <Td className="table__cell--primary">{summarize(req)}</Td>
                        <Td>{req.requester_email ?? "—"}</Td>
                        <Td className="muted">{scopeLabel(req)}</Td>
                        <Td className="muted">{timeAgo(req.created_at)}</Td>
                        <Td align="right">
                          <span className="row" style={{ justifyContent: "flex-end" }}>
                            <Button
                              variant="primary"
                              disabled={decidingId === req.id}
                              onClick={() => void decide(req, "approve")}
                            >
                              Approve
                            </Button>
                            <Button
                              variant="danger"
                              onClick={() => {
                                setRejecting(req);
                                setRejectReason("");
                              }}
                            >
                              Reject
                            </Button>
                          </span>
                        </Td>
                      </Tr>
                    ))}
                  </tbody>
                </Table>
              </TableWrap>
            ) : (
              <EmptyState
                title="Nothing to approve"
                description="Requests appear here when your memberships cover their scope."
              />
            )}
          </CardPanel>
        ) : null}

        {activeTab === "mine" ? (
          <CardPanel title="My requests">
            {mine.isError ? (
              <div style={{ padding: 16 }}>
                <QueryError what="your requests" error={mine.error} />
              </div>
            ) : mine.isLoading ? (
              <div className="stack" style={{ padding: 16 }}>
                <Skeleton width="60%" />
                <Skeleton width="80%" />
              </div>
            ) : mine.data?.items.length ? (
              <TableWrap>
                <Table>
                  <thead>
                    <tr>
                      <Th>Type</Th>
                      <Th>Request</Th>
                      <Th>Scope</Th>
                      <Th>Status</Th>
                      <Th>Decided by</Th>
                      <Th>Reason</Th>
                      <Th align="right">Actions</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {mine.data.items.map((req) => {
                      const projectHref = openProjectFor(req);
                      return (
                        <Tr key={req.id}>
                          <Td>
                            <span className="type-label">{req.type.replace("create_", "")}</span>
                          </Td>
                          <Td className="table__cell--primary">{summarize(req)}</Td>
                          <Td className="muted">{scopeLabel(req)}</Td>
                          <Td>
                            <StatusBadge status={req.status} />
                          </Td>
                          <Td className="muted">{req.approver_email ?? "—"}</Td>
                          <Td className="muted">{req.reason ?? "—"}</Td>
                          <Td align="right">
                            <span className="row" style={{ justifyContent: "flex-end" }}>
                              {projectHref ? (
                                <Link className="button" data-variant="quiet" data-size="S" to={projectHref}>
                                  Open project
                                </Link>
                              ) : null}
                              {req.status === "pending" ? (
                                <Button
                                  variant="quiet"
                                  disabled={decidingId === req.id}
                                  onClick={() => void decide(req, "cancel")}
                                >
                                  Cancel
                                </Button>
                              ) : req.status === "rejected" || req.status === "cancelled" ? (
                                <Button variant="default" onClick={() => resubmit(req)}>
                                  Resubmit
                                </Button>
                              ) : null}
                            </span>
                          </Td>
                        </Tr>
                      );
                    })}
                  </tbody>
                </Table>
              </TableWrap>
            ) : (
              <TableEmpty colSpan={7}>You have not submitted any requests yet.</TableEmpty>
            )}
          </CardPanel>
        ) : null}
      </Tabs>

      <Dialog
        open={rejecting !== null}
        title="Reject request"
        onClose={() => setRejecting(null)}
        footer={
          <>
            <Button
              variant="danger"
              disabled={!rejectReason.trim() || decidingId === rejecting?.id}
              onClick={() => rejecting && void decide(rejecting, "reject", rejectReason.trim())}
            >
              Confirm reject
            </Button>
            <Button variant="quiet" onClick={() => setRejecting(null)}>
              Cancel
            </Button>
          </>
        }
      >
        <p className="muted">
          {rejecting ? summarize(rejecting) : ""} — the reason is shown to the requester.
        </p>
        <Field label="Reason">
          <Textarea
            rows={3}
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            placeholder="Reason (required)"
            autoFocus
          />
        </Field>
      </Dialog>
    </div>
  );
}
