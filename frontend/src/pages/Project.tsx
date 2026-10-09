import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { useDirectoryProjects, useMetrics, useOverview, useProjectKeys } from "../api/hooks";
import { PageHeader } from "../components/PageHeader";
import { RefreshButton } from "../components/RefreshButton";
import { TrendChart } from "../components/charts/TrendChart";
import {
  Alert,
  Badge,
  Button,
  CardPanel,
  Dialog,
  EmptyState,
  Metric,
  QueryError,
  Skeleton,
  Table,
  TableEmpty,
  TableWrap,
  Td,
  TextInput,
  Th,
  Tr,
  useToast,
} from "../components/core";
import { IconCopy, IconKey } from "../components/core/icons";
import { useAuth } from "../state/AuthContext";
import { formatMoney, formatMs, formatPct, formatTokens } from "../lib/format";
import type { ProjectKey, ProjectKeyRow } from "../api/types";

export default function Project() {
  const { projectId = "" } = useParams();
  const { hasRole, costVisible } = useAuth();
  const canManageKeys = hasRole("engineer", "manager");
  const queryClient = useQueryClient();
  const toast = useToast();
  const projects = useDirectoryProjects();
  const overview = useOverview({ days: 30, project_id: projectId });
  const metrics = useMetrics("project", { days: 30, project_id: projectId }, projectId);
  const keys = useProjectKeys(projectId, canManageKeys);

  const [label, setLabel] = useState("");
  const [created, setCreated] = useState<ProjectKey | null>(null);
  const [rotated, setRotated] = useState<ProjectKey | null>(null);
  const [revoking, setRevoking] = useState<ProjectKeyRow | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const project = projects.data?.items.find((item) => item.project_id === projectId);
  const chartSeries = (metrics.data?.items ?? []).map((m) => ({
    day: m.day.slice(5),
    executions: m.executions,
    failed: m.failed_executions,
    cost: m.total_cost,
  }));

  const refreshKeys = () => {
    void queryClient.invalidateQueries({ queryKey: ["project-keys", projectId] });
    void queryClient.invalidateQueries({ queryKey: ["directory", "projects"] });
  };

  const addKey = async () => {
    setBusy(true);
    setError(null);
    try {
      setCreated(await api.projects.createKey(projectId, label.trim() || undefined));
      setLabel("");
      refreshKeys();
      toast.success("Ingest key added — copy it now.");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to add the key.";
      setError(message);
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  const rotateKey = async (row: ProjectKeyRow) => {
    setBusy(true);
    setError(null);
    try {
      setRotated(await api.projects.rotateKey(projectId, row.id));
      refreshKeys();
      toast.success("Key rotated — copy the new value now.");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to rotate the key.";
      setError(message);
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  const revokeKey = async () => {
    if (!revoking) return;
    setBusy(true);
    setError(null);
    try {
      await api.projects.revokeKey(projectId, revoking.id);
      setRevoking(null);
      refreshKeys();
      toast.success("Key revoked.");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to delete the key.";
      setError(message);
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  if (projects.isLoading) {
    return (
      <div className="page">
        <Skeleton shape="title" width={260} />
        <Skeleton shape="chart" />
      </div>
    );
  }

  if (projects.isError) {
    return (
      <div className="page">
        <PageHeader title="Project" />
        <QueryError what="the project" error={projects.error} />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="page">
        <PageHeader title="Project" />
        <Alert
          variant="danger"
          message="Project not found."
          detail={`No project ${projectId} is visible to your memberships.`}
          extra={
            <Link to="/projects" className="button" data-size="S">
              Back to projects
            </Link>
          }
        />
      </div>
    );
  }

  const data = overview.data;

  return (
    <div className="page">
      <PageHeader
        title={`${project.project_id} · ${project.name}`}
        subTitle={`${project.team_name} · ${project.department_name}`}
        extra={
          <>
            <Link to="/projects" className="button" data-size="S">
              All projects
            </Link>
            <RefreshButton />
          </>
        }
      />

      {overview.isError ? <QueryError what="the project overview" error={overview.error} /> : null}

      <div className="grid grid-4">
        <Metric label="Executions" value={data?.executions ?? 0} sub={`${data?.failed_executions ?? 0} failed`} />
        <Metric
          label="Error rate"
          value={formatPct(data?.error_rate)}
          tone={data && data.error_rate > 0 ? "danger" : "default"}
        />
        <Metric label="Avg duration" value={formatMs(data?.avg_duration_ms)} sub={`p95 ${formatMs(data?.p95_duration_ms)}`} />
        <Metric label="Tokens" value={formatTokens(data?.total_tokens)} sub={`${data?.llm_calls ?? 0} LLM calls`} />
      </div>

      <CardPanel title="Details" subTitle="Attribution context and ingest status">
        <div className="kv-grid">
          <div className="kv">
            <span className="kv__key">Project id</span>
            <span className="kv__value inline-code">{project.project_id}</span>
          </div>
          <div className="kv">
            <span className="kv__key">Team</span>
            <span className="kv__value">{project.team_name}</span>
          </div>
          <div className="kv">
            <span className="kv__key">Department</span>
            <span className="kv__value">{project.department_name}</span>
          </div>
          <div className="kv">
            <span className="kv__key">Status</span>
            <span className="kv__value">{project.enabled ? "enabled" : "disabled"}</span>
          </div>
          <div className="kv">
            <span className="kv__key">Active keys</span>
            <span className="kv__value">{project.active_keys}</span>
          </div>
        </div>
      </CardPanel>

      <div className="grid grid-2">
        <CardPanel title="Executions over time" subTitle="This project, last 30 days">
          <div style={{ padding: "var(--global-dimension-size-100)" }}>
            {metrics.isLoading ? (
              <Skeleton shape="chart" />
            ) : chartSeries.length ? (
              <TrendChart
                data={chartSeries}
                series={[
                  { key: "executions", label: "Executions", type: "bar", colorIndex: 6 },
                  { key: "failed", label: "Failed", type: "line", colorIndex: 3 },
                ]}
                height={220}
              />
            ) : (
              <EmptyState
                title="No activity in range"
                description="Executions appear once the SDK ingests traces for this project."
              />
            )}
          </div>
        </CardPanel>
        {costVisible ? (
          <CardPanel title="Cost over time" subTitle="USD per day">
            <div style={{ padding: "var(--global-dimension-size-100)" }}>
              {metrics.isLoading ? (
                <Skeleton shape="chart" />
              ) : chartSeries.length ? (
                <TrendChart
                  data={chartSeries}
                  series={[{ key: "cost", label: "Cost", colorIndex: 0 }]}
                  valueFormatter={(v) => formatMoney(v)}
                  height={220}
                />
              ) : (
                <EmptyState
                  title="No cost in range"
                  description="Costs appear once executions are priced."
                />
              )}
            </div>
          </CardPanel>
        ) : null}
      </div>

      {error ? <Alert variant="danger" message={error} /> : null}

      {created || rotated ? (
        <RevealKey
          apiKey={(created ?? rotated)!.api_key}
          label={(created ?? rotated)!.label}
          onDismiss={() => {
            setCreated(null);
            setRotated(null);
          }}
        />
      ) : null}

      <CardPanel
        title="Ingest API keys"
        subTitle="Redacted after creation; any active key can ingest this project"
        extra={
          canManageKeys ? (
            <span className="row">
              <TextInput
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="label (optional)"
                aria-label="Key label"
              />
              <Button variant="primary" disabled={busy} onClick={() => void addKey()}>
                <IconKey size={14} />
                Add key
              </Button>
            </span>
          ) : undefined
        }
      >
        {!canManageKeys ? (
          <EmptyState
            title="Read-only access"
            description="Engineers and managers covering this project can add, rotate and delete its ingest keys."
          />
        ) : keys.isError ? (
          <div style={{ padding: 16 }}>
            <QueryError what="the project keys" error={keys.error} />
          </div>
        ) : keys.isLoading ? (
          <div className="stack" style={{ padding: 16 }}>
            <Skeleton width="70%" />
            <Skeleton width="50%" />
          </div>
        ) : keys.data?.items.length ? (
          <TableWrap>
            <Table>
              <thead>
                <tr>
                  <Th>Label</Th>
                  <Th>Key</Th>
                  <Th>Created</Th>
                  <Th>Last used</Th>
                  <Th>Status</Th>
                  <Th align="right">Actions</Th>
                </tr>
              </thead>
              <tbody>
                {keys.data.items.map((row) => (
                  <Tr key={row.id}>
                    <Td className="table__cell--primary">{row.label ?? "—"}</Td>
                    <Td className="inline-code">{row.hint}</Td>
                    <Td className="muted num">
                      {row.created_at ? new Date(row.created_at).toLocaleString() : "—"}
                    </Td>
                    <Td className="muted num">
                      {row.last_used_at ? new Date(row.last_used_at).toLocaleString() : "never"}
                    </Td>
                    <Td>
                      <Badge variant={row.active ? "success" : "default"}>
                        {row.active ? "active" : "revoked"}
                      </Badge>
                    </Td>
                    <Td align="right">
                      {row.active ? (
                        <span className="row" style={{ justifyContent: "flex-end" }}>
                          <Button
                            variant="quiet"
                            disabled={busy}
                            onClick={() => void rotateKey(row)}
                          >
                            Rotate
                          </Button>
                          <Button
                            variant="danger"
                            disabled={busy}
                            onClick={() => setRevoking(row)}
                          >
                            Delete
                          </Button>
                        </span>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          </TableWrap>
        ) : (
          <TableEmpty colSpan={6}>
            No keys yet. Add one, then point the SDK exporter at the ingest endpoint.
          </TableEmpty>
        )}
      </CardPanel>

      <Dialog
        open={revoking !== null}
        title="Delete API key"
        onClose={() => setRevoking(null)}
        footer={
          <>
            <Button variant="danger" disabled={busy} onClick={() => void revokeKey()}>
              Delete key
            </Button>
            <Button variant="quiet" onClick={() => setRevoking(null)}>
              Cancel
            </Button>
          </>
        }
      >
        <p className="muted">
          {revoking?.label ? `“${revoking.label}” ` : ""}
          {revoking?.hint} stops authenticating immediately. It stays listed as
          revoked for audit.
        </p>
      </Dialog>
    </div>
  );
}

function RevealKey({
  apiKey,
  label,
  onDismiss,
}: {
  apiKey: string;
  label: string | null;
  onDismiss: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(apiKey);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };
  return (
    <Alert
      variant="warning"
      message={
        <>
          <IconKey size={14} /> New ingest key{label ? ` “${label}”` : ""} — copy it now,
          it will not be shown again.
        </>
      }
      detail={<code className="inline-code">{apiKey}</code>}
      extra={
        <>
          <Button variant="quiet" onClick={() => void copy()}>
            <IconCopy size={14} />
            {copied ? "Copied" : "Copy"}
          </Button>
          <Button variant="quiet" onClick={onDismiss}>
            Dismiss
          </Button>
        </>
      }
    />
  );
}
