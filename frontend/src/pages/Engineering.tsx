import { useCallback, useEffect, useState } from "react";
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
  SortableTh,
  Table,
  TableEmpty,
  TableWrap,
  Td,
  TextInput,
  Th,
  Tr,
} from "../components/core";
import { formatMoney, formatMs, formatTokens } from "../lib/format";

const PAGE_SIZE = 100;

type SortKey =
  | "started_at"
  | "duration_ms"
  | "total_tokens"
  | "total_cost"
  | "error_count"
  | "status";

export default function Engineering() {
  const { filters } = useFilters();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();

  const q = params.get("q") ?? "";
  const sort = (params.get("sort") as SortKey | null) ?? "started_at";
  const order = (params.get("order") as "asc" | "desc" | null) ?? "desc";
  const status = (params.get("status") as "" | "ok" | "error" | null) ?? "";
  const limit = Number(params.get("limit")) || PAGE_SIZE;
  const page = Math.max(1, Number(params.get("page")) || 1);
  const offset = (page - 1) * limit;

  const [searchDraft, setSearchDraft] = useState(q);
  // Keep the draft aligned with the URL (back/forward, drill-down links) by
  // adjusting state during render instead of in an effect.
  const [syncedQ, setSyncedQ] = useState(q);
  if (q !== syncedQ) {
    setSyncedQ(q);
    setSearchDraft(q);
  }

  const updateParams = useCallback(
    (changes: Record<string, string | number | undefined>) => {
      const next = new URLSearchParams(params);
      for (const [key, value] of Object.entries(changes)) {
        if (value === undefined || value === "") next.delete(key);
        else next.set(key, String(value));
      }
      setParams(next, { replace: true });
    },
    [params, setParams]
  );

  // Debounced server-side search (300 ms); resets the extended limit.
  useEffect(() => {
    if (searchDraft === q) return;
    const timer = setTimeout(
      () => updateParams({ q: searchDraft || undefined, limit: undefined, page: undefined }),
      300
    );
    return () => clearTimeout(timer);
  }, [searchDraft, q, updateParams]);

  const toggleSort = (key: string) => {
    if (key === sort) updateParams({ order: order === "asc" ? "desc" : "asc", page: undefined });
    else updateParams({ sort: key, order: "desc", page: undefined });
  };

  const { data, isLoading, isError, error, isFetching } = useExecutions(filters, {
    status: status || undefined,
    q: q || undefined,
    sort,
    order,
    limit,
    offset,
  });
  const items = data?.items ?? [];

  return (
    <div className="page">
      <PageHeader
        title="Engineering"
        subTitle="Trace explorer — every agent execution with status, latency and cost."
        extra={
          <>
            <TextInput
              variant="search"
              value={searchDraft}
              aria-label="Search executions"
              placeholder="Search trace, workflow, error…"
              onChange={(e) => setSearchDraft(e.target.value)}
            />
            <Select
              value={status}
              aria-label="Filter by status"
              onChange={(e) => {
              updateParams({ status: e.target.value || undefined, limit: undefined, page: undefined });
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
          isLoading
            ? "Loading…"
            : `${items.length}${data && data.total > items.length ? ` of ${data.total}` : ""} in range`
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
                  <SortableTh
                    sortKey="status"
                    active={sort === "status"}
                    direction={order}
                    onSort={toggleSort}
                  >
                    Status
                  </SortableTh>
                  <Th>Failure kind</Th>
                  <SortableTh
                    sortKey="duration_ms"
                    active={sort === "duration_ms"}
                    direction={order}
                    onSort={toggleSort}
                    align="right"
                  >
                    Duration
                  </SortableTh>
                  <SortableTh
                    sortKey="total_tokens"
                    active={sort === "total_tokens"}
                    direction={order}
                    onSort={toggleSort}
                    align="right"
                  >
                    Tokens
                  </SortableTh>
                  <SortableTh
                    sortKey="total_cost"
                    active={sort === "total_cost"}
                    direction={order}
                    onSort={toggleSort}
                    align="right"
                  >
                    Cost
                  </SortableTh>
                  <SortableTh
                    sortKey="started_at"
                    active={sort === "started_at"}
                    direction={order}
                    onSort={toggleSort}
                  >
                    Started
                  </SortableTh>
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
                        {!e.cost_complete && (e.unpriced_calls ?? 0) > 0 ? (
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
                  No executions in range. <Link to="/requests">Register a project</Link>{" "}
                  or point the SDK at the ingest endpoint, then widen the filters if needed.
                </TableEmpty>
              )}
            </Table>
          </TableWrap>
        )}
        {!isLoading && data && data.total > 0 ? (
          <div
            className="row"
            style={{ justifyContent: "space-between", padding: 12, gap: 12, flexWrap: "wrap" }}
          >
            <span className="muted">
              Showing {offset + 1}–{Math.min(offset + items.length, data.total)} of {data.total}
            </span>
            <span className="row" style={{ gap: 8, alignItems: "center" }}>
              <Select
                value={String(limit)}
                aria-label="Rows per page"
                onChange={(e) =>
                  updateParams({ limit: Number(e.target.value), page: undefined })
                }
              >
                <option value="25">25 / page</option>
                <option value="50">50 / page</option>
                <option value="100">100 / page</option>
              </Select>
              <Button
                variant="quiet"
                disabled={page <= 1}
                onClick={() => updateParams({ page: page - 1 })}
              >
                Prev
              </Button>
              <Button
                variant="quiet"
                disabled={offset + items.length >= data.total}
                onClick={() => updateParams({ page: page + 1 })}
              >
                Next
              </Button>
            </span>
          </div>
        ) : null}
      </CardPanel>
    </div>
  );
}
