import { useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { useDirectoryProjects, useMyTeams, useOverview } from "../api/hooks";
import { useAuth } from "../state/AuthContext";
import { useFilters } from "../state/FiltersContext";
import { PageHeader } from "../components/PageHeader";
import { FilterChips, FiltersControl } from "../components/FiltersControl";
import { RefreshButton } from "../components/RefreshButton";
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
  Skeleton,
  Table,
  TableWrap,
  Td,
  TextInput,
  Th,
  Tr,
  useToast,
} from "../components/core";
import { formatMoney, formatPct, formatTokens } from "../lib/format";
import type { DirectoryProject } from "../api/types";

export default function Projects() {
  const { filters } = useFilters();
  const { costVisible, hasRole } = useAuth();
  const projects = useDirectoryProjects();
  const canAddProject = hasRole("admin", "exec", "manager", "engineer");
  const [adding, setAdding] = useState(false);

  return (
    <div className="page">
      <PageHeader
        title="Projects"
        subTitle="Every project you belong to, with a usage overview and its ingest keys."
        extra={
          <>
            {canAddProject ? (
              <Button variant="primary" onClick={() => setAdding(true)}>
                Add project
              </Button>
            ) : null}
            <FiltersControl dimensions={["days"]} />
            <RefreshButton />
          </>
        }
      />
      <FilterChips dimensions={["days"]} />

      {projects.isError ? <QueryError what="projects" error={projects.error} /> : null}

      <CardPanel
        title="Projects"
        subTitle={
          projects.data
            ? `${projects.data.total} visible with your memberships`
            : undefined
        }
      >
        {projects.isLoading ? (
          <div className="stack" style={{ padding: 16 }}>
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} shape="text" width="100%" />
            ))}
          </div>
        ) : projects.data?.items.length ? (
          <TableWrap>
            <Table interactive>
              <thead>
                <tr>
                  <Th>Project</Th>
                  <Th>Team</Th>
                  <Th>Department</Th>
                  <Th align="right">Executions</Th>
                  <Th align="right">Error rate</Th>
                  <Th align="right">Tokens</Th>
                  {costVisible ? <Th align="right">Cost</Th> : null}
                  <Th align="right">Keys</Th>
                </tr>
              </thead>
              <tbody>
                {projects.data.items.map((project) => (
                  <ProjectRow
                    key={project.id}
                    project={project}
                    days={filters.days}
                    costVisible={costVisible}
                  />
                ))}
              </tbody>
            </Table>
          </TableWrap>
        ) : (
          <EmptyState
            title="No projects yet"
            description="Add a project to one of your teams — it appears here once approved."
            extra={<Link to="/requests">Open Requests</Link>}
          />
        )}
      </CardPanel>

      {adding ? <AddProjectDialog onClose={() => setAdding(false)} /> : null}
    </div>
  );
}

function AddProjectDialog({ onClose }: { onClose: () => void }) {
  const teams = useMyTeams();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [name, setName] = useState("");
  const [teamId, setTeamId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const options = (teams.data?.items ?? []).map((team) => ({
    value: team.id,
    label: `${team.name} (${team.department_name})`,
  }));

  const submit = async () => {
    const trimmed = name.trim();
    if (!trimmed || !teamId) {
      setError("Enter a project name and select one of your teams.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await api.requests.create("create_project", {
        name: trimmed,
        team_id: teamId,
      });
      await queryClient.invalidateQueries({ queryKey: ["directory"] });
      if (result.status === "approved") {
        toast.success("Project added to the team.");
      } else {
        toast.success("Project request submitted for a manager's approval.");
      }
      onClose();
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to add the project.";
      setError(message);
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open
      title="Add project"
      onClose={onClose}
      footer={
        <>
          <Button
            variant="primary"
            disabled={busy || !name.trim() || !teamId}
            onClick={() => void submit()}
          >
            {busy ? "Adding…" : "Add project"}
          </Button>
          <Button variant="quiet" onClick={onClose}>
            Cancel
          </Button>
        </>
      }
    >
      <div className="stack">
        {error ? <Alert variant="danger" message={error} /> : null}
        <p className="muted" style={{ margin: 0 }}>
          Projects belong to a team. Choose one of your teams; a manager covering
          it approves the new project when needed.
        </p>
        <Field label="Project name">
          <TextInput
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Demo Project"
            autoFocus
          />
        </Field>
        {teams.isLoading ? (
          <Skeleton width="70%" />
        ) : options.length ? (
          <Field label="Team">
            <SearchableSelect
              value={teamId}
              onChange={setTeamId}
              options={options}
              placeholder="Select one of your teams…"
              aria-label="Project team"
            />
          </Field>
        ) : (
          <EmptyState
            title="No teams yet"
            description="You need a team membership before adding a project."
            extra={<Link to="/requests">Request a membership</Link>}
          />
        )}
      </div>
    </Dialog>
  );
}

function ProjectRow({
  project,
  days,
  costVisible,
}: {
  project: DirectoryProject;
  days: number;
  costVisible: boolean;
}) {
  const overview = useOverview({ days, project_id: project.project_id });
  const data = overview.data;

  return (
    <Tr>
      <Td>
        <Link to={`/projects/${project.project_id}`} className="table__cell--primary">
          {project.name}
        </Link>
      </Td>
      <Td>{project.team_name}</Td>
      <Td className="muted">{project.department_name}</Td>
      <Td align="right" className="num">
        {overview.isLoading ? "…" : (data?.executions ?? 0)}
      </Td>
      <Td align="right" className="num">
        {overview.isLoading ? "…" : formatPct(data?.error_rate)}
      </Td>
      <Td align="right" className="num">
        {overview.isLoading ? "…" : formatTokens(data?.total_tokens)}
      </Td>
      {costVisible ? (
        <Td align="right" className="num">
          {overview.isLoading ? "…" : formatMoney(data?.total_cost)}
        </Td>
      ) : null}
      <Td align="right">
        <Badge variant={project.has_keys ? "success" : "warning"}>
          {project.active_keys}
        </Badge>
      </Td>
    </Tr>
  );
}
