import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import {
  useAlertChannels,
  useAlertRules,
  useAlerts,
  useDepartments,
  useDirectoryProjects,
  useTeams,
} from "../api/hooks";
import type {
  Alert,
  AlertChannel,
  AlertRule,
  AlertRuleInput,
  AlertMetric,
  ScopeType,
} from "../api/types";
import { useAuth } from "../state/AuthContext";
import { PageHeader } from "../components/PageHeader";
import { RefreshButton } from "../components/RefreshButton";
import { SeverityBadge } from "../components/domain";
import {
  Alert as AlertBanner,
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
  TextInput,
  Th,
  Tr,
  useToast,
} from "../components/core";

type TabId = "open" | "rules" | "channels";

const METRIC_LABELS: Record<AlertMetric, string> = {
  error_rate: "Error rate",
  daily_tokens: "Daily tokens",
  tool_calls_per_execution: "Tool calls / execution",
  p95_latency: "P95 latency (ms)",
  cost_anomaly: "Cost anomaly (× 7-day avg)",
};

export default function Alerts() {
  const { hasRole } = useAuth();
  const canManageRules = hasRole("manager", "exec");
  const canManageChannels = hasRole("exec");
  const [tab, setTab] = useState<TabId>("open");
  const queryClient = useQueryClient();
  const { data: openAlerts } = useAlerts();

  const tabs = [
    { id: "open" as const, label: "Open", counter: openAlerts?.total },
    ...(canManageRules ? [{ id: "rules" as const, label: "Rules" }] : []),
    ...(canManageChannels ? [{ id: "channels" as const, label: "Channels" }] : []),
  ];
  const activeTab = tabs.some((t) => t.id === tab) ? tab : "open";

  return (
    <div className="page">
      <PageHeader
        title="Alerts"
        subTitle="Scoped notifications, threshold rules and delivery channels."
        extra={<RefreshButton />}
      />
      <Tabs tabs={tabs} selected={activeTab} onSelect={(id) => setTab(id as TabId)}>
        {activeTab === "open" ? <OpenAlertsPanel /> : null}
        {activeTab === "rules" ? (
          <RulesPanel canGlobal={canManageChannels} onChanged={() => void queryClient.invalidateQueries()} />
        ) : null}
        {activeTab === "channels" ? <ChannelsPanel /> : null}
      </Tabs>
      {(activeTab === "rules" || activeTab === "channels") &&
      !canManageChannels ? (
        <AlertBanner
          variant="info"
          message="Managers manage rules for their org units; channels are managed by exec/admin."
        />
      ) : null}
    </div>
  );
}

function OpenAlertsPanel() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [status, setStatus] = useState("open");
  const [severity, setSeverity] = useState("");
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => setQ(search.trim()), 300);
    return () => clearTimeout(timer);
  }, [search]);

  const alerts = useAlerts(true, {
    status: status || undefined,
    severity: severity || undefined,
    q: q || undefined,
    limit: 200,
  });
  const items = alerts.data?.items ?? [];

  const update = async (alert: Alert, next: string) => {
    setBusyId(alert.id);
    setError(null);
    try {
      await api.alerts.update(alert.id, next);
      toast.success(next === "closed" ? "Alert closed." : "Alert acknowledged.");
      void queryClient.invalidateQueries({ queryKey: ["alerts"] });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to update the alert.";
      setError(message);
      toast.error(message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <CardPanel
      title="Alerts"
      subTitle={alerts.data ? `${alerts.data.total} matching` : undefined}
      extra={
        <span className="row" style={{ gap: 8 }}>
          <TextInput
            variant="search"
            value={search}
            aria-label="Search alerts"
            placeholder="Search message…"
            onChange={(e) => setSearch(e.target.value)}
          />
          <Select
            value={severity}
            aria-label="Filter by severity"
            onChange={(e) => setSeverity(e.target.value)}
          >
            <option value="">All severities</option>
            <option value="warning">Warning</option>
            <option value="critical">Critical</option>
          </Select>
          <Select
            value={status}
            aria-label="Filter by status"
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="open">Open</option>
            <option value="acknowledged">Acknowledged</option>
            <option value="closed">Closed</option>
            <option value="">All statuses</option>
          </Select>
        </span>
      }
    >
      {error ? <AlertBanner variant="danger" message={error} /> : null}
      {alerts.isError ? <QueryError what="alerts" error={alerts.error} /> : null}
      {alerts.isLoading ? (
        <div className="stack" style={{ padding: 16 }}>
          <Skeleton width="70%" />
          <Skeleton width="50%" />
        </div>
      ) : items.length ? (
        <div className="stack stack--loose" style={{ padding: "var(--global-dimension-size-200)" }}>
          {items.map((alert) => (
            <div key={alert.id} className="row" style={{ gap: 12, alignItems: "center" }}>
              <SeverityBadge severity={alert.severity} />
              <div className="list-row__main" style={{ flex: 1, minWidth: 0 }}>
                <span className="truncate">{alert.message}</span>
                <span className="muted" style={{ fontSize: 12 }}>
                  {alert.scope ? `${alert.scope}` : alert.dimension}
                  {alert.scope_name ? ` · ${alert.scope_name}` : ""}
                  {alert.triggered_at ? ` · ${new Date(alert.triggered_at).toLocaleString()}` : ""}
                </span>
              </div>
              <Badge variant={alert.status === "open" ? "warning" : "default"}>
                {alert.status}
              </Badge>
              {alert.can_ack && alert.status !== "acknowledged" ? (
                <Button
                  variant="quiet"
                  disabled={busyId === alert.id}
                  onClick={() => void update(alert, "acknowledged")}
                >
                  Ack
                </Button>
              ) : null}
              {alert.can_ack && alert.status !== "closed" ? (
                <Button
                  variant="quiet"
                  disabled={busyId === alert.id}
                  onClick={() => void update(alert, "closed")}
                >
                  Close
                </Button>
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <EmptyState
          title="No alerts match"
          description="Alerts appear when a threshold rule or budget crosses its configured limit."
        />
      )}
    </CardPanel>
  );
}

function RulesPanel({ canGlobal, onChanged }: { canGlobal: boolean; onChanged: () => void }) {
  const rules = useAlertRules();
  const toast = useToast();
  const [editing, setEditing] = useState<AlertRule | null>(null);
  const [adding, setAdding] = useState(false);
  const [deleting, setDeleting] = useState<AlertRule | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = async (rule: AlertRule) => {
    setBusy(true);
    setError(null);
    try {
      await api.alertRules.update(rule.id, { enabled: !rule.enabled });
      toast.success(rule.enabled ? "Rule disabled." : "Rule enabled.");
      onChanged();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to update the rule.";
      setError(message);
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!deleting) return;
    setBusy(true);
    setError(null);
    try {
      await api.alertRules.remove(deleting.id);
      setDeleting(null);
      toast.success("Rule deleted.");
      onChanged();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to delete the rule.";
      setError(message);
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <CardPanel
      title="Threshold rules"
      subTitle="Warning and critical alerts evaluated per UTC day"
      extra={
        <Button variant="primary" onClick={() => setAdding(true)}>
          New rule
        </Button>
      }
    >
      {error ? <AlertBanner variant="danger" message={error} /> : null}
      {rules.isError ? <QueryError what="alert rules" error={rules.error} /> : null}
      {rules.isLoading ? (
        <div style={{ padding: 16 }}>
          <Skeleton width="60%" />
        </div>
      ) : (
        <TableWrap>
          <Table>
            <thead>
              <tr>
                <Th>Rule</Th>
                <Th>Metric</Th>
                <Th align="right">Warning</Th>
                <Th align="right">Critical</Th>
                <Th>Scope</Th>
                <Th>Channels</Th>
                <Th>Status</Th>
                <Th align="right">Actions</Th>
              </tr>
            </thead>
            {rules.data?.items.length ? (
              <tbody>
                {rules.data.items.map((rule) => (
                  <Tr key={rule.id}>
                    <Td className="table__cell--primary">
                      {rule.name} {rule.builtin ? <Badge variant="info">system</Badge> : null}
                    </Td>
                    <Td>{METRIC_LABELS[rule.metric] ?? rule.metric}</Td>
                    <Td align="right" className="num">{rule.warning_threshold}</Td>
                    <Td align="right" className="num">{rule.critical_threshold}</Td>
                    <Td>{rule.scope_type === "global" ? "Global" : rule.scope_name ?? rule.scope_type}</Td>
                    <Td>{rule.channel_ids.length ? `${rule.channel_ids.length} linked` : "fallback webhook"}</Td>
                    <Td>
                      <Badge variant={rule.enabled ? "success" : "default"}>
                        {rule.enabled ? "enabled" : "disabled"}
                      </Badge>
                    </Td>
                    <Td align="right">
                      <span className="row" style={{ justifyContent: "flex-end", gap: 6 }}>
                        <Button
                          variant="quiet"
                          disabled={busy}
                          onClick={() => void toggle(rule)}
                        >
                          {rule.enabled ? "Disable" : "Enable"}
                        </Button>
                        <Button variant="quiet" onClick={() => setEditing(rule)}>
                          Edit
                        </Button>
                        {!rule.builtin ? (
                          <Button variant="danger" onClick={() => setDeleting(rule)}>
                            Delete
                          </Button>
                        ) : null}
                      </span>
                    </Td>
                  </Tr>
                ))}
              </tbody>
            ) : (
              <TableEmpty colSpan={8}>No rules visible to your memberships.</TableEmpty>
            )}
          </Table>
        </TableWrap>
      )}

      {adding || editing ? (
        <RuleDialog
          key={editing?.id ?? "new"}
          rule={editing}
          canGlobal={canGlobal}
          onClose={() => {
            setAdding(false);
            setEditing(null);
          }}
          onSaved={() => {
            setAdding(false);
            setEditing(null);
            onChanged();
          }}
        />
      ) : null}

      <Dialog
        open={deleting !== null}
        title="Delete rule"
        onClose={() => setDeleting(null)}
        footer={
          <>
            <Button variant="danger" disabled={busy} onClick={() => void remove()}>
              Delete rule
            </Button>
            <Button variant="quiet" onClick={() => setDeleting(null)}>
              Cancel
            </Button>
          </>
        }
      >
        <p className="muted">
          “{deleting?.name}” stops producing alerts. Existing alerts stay listed.
        </p>
      </Dialog>
    </CardPanel>
  );
}

function RuleDialog({
  rule,
  canGlobal,
  onClose,
  onSaved,
}: {
  rule: AlertRule | null;
  canGlobal: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const channels = useAlertChannels(true);
  const departments = useDepartments();
  const teams = useTeams();
  const projects = useDirectoryProjects();
  const toast = useToast();

  const [name, setName] = useState(rule?.name ?? "");
  const [metric, setMetric] = useState<AlertMetric>(rule?.metric ?? "error_rate");
  const [warning, setWarning] = useState(rule ? String(rule.warning_threshold) : "0.5");
  const [critical, setCritical] = useState(rule ? String(rule.critical_threshold) : "1");
  const [scopeType, setScopeType] = useState<ScopeType>(
    rule?.scope_type ?? (canGlobal ? "global" : "project")
  );
  const [scopeId, setScopeId] = useState(rule?.scope_id ?? "");
  const [channelIds, setChannelIds] = useState<string[]>(rule?.channel_ids ?? []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const scopeOptions =
    scopeType === "department"
      ? (departments.data?.items ?? []).map((d) => ({ value: d.id, label: d.name }))
      : scopeType === "team"
        ? (teams.data?.items ?? []).map((t) => ({
            value: t.id,
            label: `${t.name} (${t.department_name})`,
          }))
        : (projects.data?.items ?? []).map((p) => ({
            value: p.id,
            label: `${p.project_id} · ${p.name}`,
          }));

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const w = Number(warning);
      const c = Number(critical);
      if (!Number.isFinite(w) || !Number.isFinite(c)) {
        throw new Error("Thresholds must be numbers.");
      }
      if (c < w) throw new Error("Critical threshold must be ≥ the warning threshold.");
      if (scopeType !== "global" && !scopeId) {
        throw new Error("Pick a scope for the rule.");
      }
      const payload: AlertRuleInput = {
        name: name.trim(),
        metric,
        warning_threshold: w,
        critical_threshold: c,
        scope_type: scopeType,
        scope_id: scopeType === "global" ? null : scopeId,
        channel_ids: channelIds,
      };
      if (!payload.name) throw new Error("Name is required.");
      if (rule) await api.alertRules.update(rule.id, payload);
      else await api.alertRules.create(payload);
      toast.success(rule ? "Rule saved." : "Rule created.");
      onSaved();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to save the rule.";
      setError(message);
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open
      title={rule ? `Edit rule — ${rule.name}` : "New alert rule"}
      onClose={onClose}
      footer={
        <>
          <Button variant="primary" disabled={busy} onClick={() => void submit()}>
            {rule ? "Save changes" : "Create rule"}
          </Button>
          <Button variant="quiet" onClick={onClose}>
            Cancel
          </Button>
        </>
      }
    >
      <div className="stack">
        {error ? <AlertBanner variant="danger" message={error} /> : null}
        <Field label="Name">
          <TextInput value={name} onChange={(e) => setName(e.target.value)} placeholder="Team A error rate" />
        </Field>
        <div className="row" style={{ gap: 12, alignItems: "flex-end" }}>
          <Field label="Metric">
            <Select
              value={metric}
              aria-label="Rule metric"
              onChange={(e) => setMetric(e.target.value as AlertMetric)}
            >
              {Object.entries(METRIC_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Warning threshold">
            <TextInput value={warning} inputMode="decimal" onChange={(e) => setWarning(e.target.value)} />
          </Field>
          <Field label="Critical threshold">
            <TextInput value={critical} inputMode="decimal" onChange={(e) => setCritical(e.target.value)} />
          </Field>
        </div>
        <div className="row" style={{ gap: 12, alignItems: "flex-end" }}>
          <Field label="Scope">
            <Select
              value={scopeType}
              aria-label="Rule scope type"
              onChange={(e) => {
                setScopeType(e.target.value as ScopeType);
                setScopeId("");
              }}
            >
              {canGlobal ? <option value="global">Global (all projects)</option> : null}
              <option value="department">Department</option>
              <option value="team">Team</option>
              <option value="project">Project</option>
            </Select>
          </Field>
          {scopeType !== "global" ? (
            <div style={{ flex: 1 }}>
              <Field label="Scope target">
                <SearchableSelect
                  value={scopeId}
                  onChange={setScopeId}
                  options={scopeOptions}
                  placeholder="Select…"
                  aria-label="Rule scope target"
                />
              </Field>
            </div>
          ) : null}
        </div>
        <Field label="Channels (none = fallback webhook)">
          <div className="stack" style={{ gap: 4 }}>
            {(channels.data?.items ?? []).filter((c) => c.enabled).length ? (
              (channels.data?.items ?? [])
                .filter((c) => c.enabled)
                .map((channel) => (
                  <label key={channel.id} className="row" style={{ gap: 8 }}>
                    <input
                      type="checkbox"
                      checked={channelIds.includes(channel.id)}
                      onChange={(e) => {
                        setChannelIds((prev) =>
                          e.target.checked
                            ? [...prev, channel.id]
                            : prev.filter((id) => id !== channel.id)
                        );
                      }}
                    />
                    <span>
                      {channel.name} <span className="muted">({channel.type})</span>
                    </span>
                  </label>
                ))
            ) : (
              <span className="muted">No enabled channels — alerts fall back to the global webhook.</span>
            )}
          </div>
        </Field>
      </div>
    </Dialog>
  );
}

function ChannelsPanel() {
  const channels = useAlertChannels();
  const toast = useToast();
  const [editing, setEditing] = useState<AlertChannel | null>(null);
  const [adding, setAdding] = useState(false);
  const [deleting, setDeleting] = useState<AlertChannel | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const remove = async () => {
    if (!deleting) return;
    setBusy(true);
    setError(null);
    try {
      await api.alertChannels.remove(deleting.id);
      setDeleting(null);
      toast.success("Channel deleted.");
      void channels.refetch();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to delete the channel.";
      setError(message);
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <CardPanel
      title="Delivery channels"
      subTitle="Email (SMTP), Slack-compatible and generic webhooks"
      extra={
        <Button variant="primary" onClick={() => setAdding(true)}>
          New channel
        </Button>
      }
    >
      {error ? <AlertBanner variant="danger" message={error} /> : null}
      {channels.isError ? <QueryError what="alert channels" error={channels.error} /> : null}
      {channels.isLoading ? (
        <div style={{ padding: 16 }}>
          <Skeleton width="60%" />
        </div>
      ) : (
        <TableWrap>
          <Table>
            <thead>
              <tr>
                <Th>Name</Th>
                <Th>Type</Th>
                <Th>Target</Th>
                <Th>Status</Th>
                <Th align="right">Actions</Th>
              </tr>
            </thead>
            {channels.data?.items.length ? (
              <tbody>
                {channels.data.items.map((channel) => (
                  <Tr key={channel.id}>
                    <Td className="table__cell--primary">{channel.name}</Td>
                    <Td>
                      <Badge variant={channel.type === "email" ? "info" : "default"}>
                        {channel.type}
                      </Badge>
                    </Td>
                    <Td className="inline-code truncate" style={{ maxWidth: 260 }}>
                      {channel.target}
                    </Td>
                    <Td>
                      <Badge variant={channel.enabled ? "success" : "default"}>
                        {channel.enabled ? "enabled" : "disabled"}
                      </Badge>
                    </Td>
                    <Td align="right">
                      <span className="row" style={{ justifyContent: "flex-end", gap: 6 }}>
                        <Button variant="quiet" onClick={() => setEditing(channel)}>
                          Edit
                        </Button>
                        <Button variant="danger" onClick={() => setDeleting(channel)}>
                          Delete
                        </Button>
                      </span>
                    </Td>
                  </Tr>
                ))}
              </tbody>
            ) : (
              <TableEmpty colSpan={5}>
                No channels yet. Rules without channels use the global webhook.
              </TableEmpty>
            )}
          </Table>
        </TableWrap>
      )}

      {adding || editing ? (
        <ChannelDialog
          key={editing?.id ?? "new"}
          channel={editing}
          onClose={() => {
            setAdding(false);
            setEditing(null);
          }}
          onSaved={() => {
            setAdding(false);
            setEditing(null);
            void channels.refetch();
          }}
        />
      ) : null}

      <Dialog
        open={deleting !== null}
        title="Delete channel"
        onClose={() => setDeleting(null)}
        footer={
          <>
            <Button variant="danger" disabled={busy} onClick={() => void remove()}>
              Delete channel
            </Button>
            <Button variant="quiet" onClick={() => setDeleting(null)}>
              Cancel
            </Button>
          </>
        }
      >
        <p className="muted">
          “{deleting?.name}” stops receiving alerts; rules that used it fall back
          to the global webhook.
        </p>
      </Dialog>
    </CardPanel>
  );
}

function ChannelDialog({
  channel,
  onClose,
  onSaved,
}: {
  channel: AlertChannel | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(channel?.name ?? "");
  const [type, setType] = useState<AlertChannel["type"]>(channel?.type ?? "webhook");
  const [target, setTarget] = useState(channel?.target ?? "");
  const [enabled, setEnabled] = useState(channel?.enabled ?? true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const body = { name: name.trim(), type, target: target.trim(), enabled };
      if (!body.name || !body.target) throw new Error("Name and target are required.");
      if (type === "email" && !body.target.includes("@")) {
        throw new Error("Enter an email address.");
      }
      if (type !== "email" && !/^https?:\/\//.test(body.target)) {
        throw new Error("Enter an http(s) URL.");
      }
      if (channel) await api.alertChannels.update(channel.id, body);
      else await api.alertChannels.create(body);
      toast.success(channel ? "Channel saved." : "Channel created.");
      onSaved();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to save the channel.";
      setError(message);
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open
      title={channel ? `Edit channel — ${channel.name}` : "New channel"}
      onClose={onClose}
      footer={
        <>
          <Button variant="primary" disabled={busy} onClick={() => void submit()}>
            {channel ? "Save changes" : "Create channel"}
          </Button>
          <Button variant="quiet" onClick={onClose}>
            Cancel
          </Button>
        </>
      }
    >
      <div className="stack">
        {error ? <AlertBanner variant="danger" message={error} /> : null}
        <Field label="Name">
          <TextInput value={name} onChange={(e) => setName(e.target.value)} placeholder="Ops email" />
        </Field>
        <div className="row" style={{ gap: 12, alignItems: "flex-end" }}>
          <Field label="Type">
            <Select
              value={type}
              aria-label="Channel type"
              onChange={(e) => setType(e.target.value as AlertChannel["type"])}
            >
              <option value="email">Email</option>
              <option value="slack">Slack (webhook)</option>
              <option value="webhook">Generic webhook</option>
            </Select>
          </Field>
          <div style={{ flex: 1 }}>
            <Field label={type === "email" ? "Email address" : "Webhook URL"}>
              <TextInput
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                placeholder={type === "email" ? "ops@example.com" : "https://hooks.slack.com/…"}
              />
            </Field>
          </div>
        </div>
        <label className="row" style={{ gap: 8 }}>
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          <span>Enabled</span>
        </label>
        {type === "email" ? (
          <p className="muted" style={{ margin: 0 }}>
            Email delivery needs `AIOBS_SMTP_HOST` and `AIOBS_SMTP_FROM` on the
            backend; otherwise the send is skipped with a warning.
          </p>
        ) : null}
      </div>
    </Dialog>
  );
}
