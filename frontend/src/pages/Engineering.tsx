import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useExecutions } from "../api/hooks";
import { useFilters } from "../state/FiltersContext";
import { PageHeader } from "../components/PageHeader";
import { FilterToolbar } from "../components/FilterToolbar";
import { RefreshButton } from "../components/RefreshButton";
import { StatusBadge } from "../components/domain";
import {
  Badge,
  Button,
  CardPanel,
  Select,
  Skeleton,
  QueryError,
  Table,
  TableEmpty,
  TableWrap,
  Td,
  Th,
  Tr,
} from "../components/core";
import { formatMoney, formatMs, formatTokens } from "../lib/format";

const PAGE_SIZE = 100;

export default function Engineering() {
  const { filters, setFilters } = useFilters();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [status, setStatus] = useState<"" | "ok" | "error">("");
  const [limit, setLimit] = useState(PAGE_SIZE);
  const appliedDrilldown = useRef(false);

  // Manager breakdown links arrive as `?workflow=` / `?client_id=` — fold them
  // into the shared filters once so the table is scoped on arrival.
  useEffect(() => {
    if (appliedDrilldown.current) return;
    appliedDrilldown.current = true;
    const workflow = searchParams.get("workflow") ?? undefined;
    const clientId = searchParams.get("client_id") ?? undefined;
    if (workflow || clientId) {
      setFilters({ ...filters, workflow, client_id: clientId });
    }
  }, [searchParams, filters, setFilters]);

  const { data, isLoading, isError, error, isFetching } = useExecutions(
    filters,
    status || undefined,
    limit
  );
  const items = data?.items ?? [];

  return (
    <div className="page">
      <PageHeader
        title="Engineering"
        subTitle="Trace explorer — every agent execution with status, latency and cost."
        extra={
          <>
            <Select
              value={status}
              aria-label="Filter by status"
              onChange={(e) => {
                setStatus(e.target.value as "" | "ok" | "error");
                setLimit(PAGE_SIZE);
              }}
            >
              <option value="">All statuses</option>
              <option value="ok">Succeeded</option>
              <option value="error">Failed</option>
            </Select>
            <RefreshButton />
          </>
        }
      />
      <FilterToolbar />

      {isError ? <QueryError what="executions" error={error} /> : null}

      <CardPanel
        title="Executions"
        subTitle={
          isLoading ? "Loading…" : `${items.length}${data && data.total > items.length ? ` of ${data.total}` : ""} in range`
        }
        extra={isFetching && !isLoading ? <Badge variant="info">Refreshing</Badge> : undefined}
      >
        {isLoading ? (
          <div className="stack" style={{ padding: 16 }}>
            {Array.from({ length: 6 }, (_, i) => (
              <Skeleton key={i} shape="text" width="100%" />
            ))}
          </div>
        ) : (
          <TableWrap>
            <Table interactive={items.length > 0}>
              <thead>
                <tr>
                  <Th>Workflow</Th>
                  <Th>Client</Th>
                  <Th>Status</Th>
                  <Th>Failure kind</Th>
                  <Th align="right">Duration</Th>
                  <Th align="right">Tokens</Th>
                  <Th align="right">Cost</Th>
                  <Th>Started</Th>
                </tr>
              </thead>
              {items.length > 0 ? (
                <tbody>
                  {items.map((e) => (
                    <Tr key={e.id} onClick={() => navigate(`/engineering/${e.id}`)}>
                      <Td>
                        <Link
                          to={`/engineering/${e.id}`}
                          className="table__cell--primary truncate"
                          onClick={(ev) => ev.stopPropagation()}
                        >
                          {e.workflow ?? e.trace_id}
                        </Link>
                        {e.workflow_version ? (
                          <span className="muted" style={{ fontSize: 12 }}>
                            {" "}
                            v{e.workflow_version}
                          </span>
                        ) : null}
                      </Td>
                      <Td>{e.client_id ?? "—"}</Td>
                      <Td>
                        <StatusBadge status={e.status} />
                      </Td>
                      <Td>{e.error_kind ?? "—"}</Td>
                      <Td align="right" className="num">
                        {formatMs(e.duration_ms)}
                      </Td>
                      <Td align="right" className="num">
                        {formatTokens(e.total_tokens)}
                      </Td>
                      <Td align="right" className="num">
                        {formatMoney(e.total_cost)}
                        {!e.cost_complete && e.unpriced_calls > 0 ? (
                          <span className="muted" title="Some calls have no configured price">
                            {" "}
                            *
                          </span>
                        ) : null}
                      </Td>
                      <Td className="muted num">
                        {e.started_at ? new Date(e.started_at).toLocaleString() : "—"}
                      </Td>
                    </Tr>
                  ))}
                </tbody>
              ) : (
                <TableEmpty colSpan={8}>
                  No executions in range. Point the SDK at the ingest endpoint, or widen the filters.
                </TableEmpty>
              )}
            </Table>
          </TableWrap>
        )}
        {!isLoading && items.length >= limit ? (
          <div className="row" style={{ justifyContent: "center", padding: 12 }}>
            <Button onClick={() => setLimit(limit + PAGE_SIZE)}>Load more</Button>
          </div>
        ) : null}
      </CardPanel>
    </div>
  );
}
