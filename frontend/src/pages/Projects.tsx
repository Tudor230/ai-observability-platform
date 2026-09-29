import { Link } from "react-router-dom";
import { useDirectoryProjects, useOverview } from "../api/hooks";
import { useAuth } from "../state/AuthContext";
import { useFilters } from "../state/FiltersContext";
import { PageHeader } from "../components/PageHeader";
import { FilterToolbar } from "../components/FilterToolbar";
import { RefreshButton } from "../components/RefreshButton";
import {
  Badge,
  CardPanel,
  EmptyState,
  QueryError,
  Skeleton,
  Table,
  TableWrap,
  Td,
  Th,
  Tr,
} from "../components/core";
import { formatMoney, formatPct, formatTokens } from "../lib/format";
import type { DirectoryProject } from "../api/types";

export default function Projects() {
  const { filters } = useFilters();
  const { costVisible } = useAuth();
  const projects = useDirectoryProjects();

  return (
    <div className="page">
      <PageHeader
        title="Projects"
        subTitle="Every project you belong to, with a usage overview and its ingest keys."
        extra={<RefreshButton />}
      />
      <FilterToolbar />

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
            description="Register a project through Requests — it appears here once approved."
          />
        )}
      </CardPanel>
    </div>
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
        <div className="muted inline-code" style={{ fontSize: 12 }}>
          {project.project_id}
        </div>
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
