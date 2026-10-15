import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  CardPanel,
  EmptyState,
  Pagination,
  Skeleton,
  Table,
  TableWrap,
  Tabs,
  Td,
  Th,
  Tr,
} from "../components/core";

export interface CostDetailRow {
  key: string;
  cells: ReactNode[];
}

/**
 * Two-view cost card (refinements v3): a breakdown (bars) and a detail table
 * over the same query result, switched with `Tabs`. The detail table is
 * height-capped (sticky header + scroll) and paginates client-side at
 * `pageSize` rows (10 by default).
 */
export function CostCard({
  title,
  subTitle,
  breakdown,
  columns,
  rows,
  emptyBreakdown,
  emptyDetail,
  loading = false,
  pageSize = 10,
  drilldown,
  filters,
  filterChips,
}: {
  title: string;
  subTitle?: string;
  breakdown: ReactNode;
  /** Detail header labels; the first column is the primary (left) one. */
  columns: string[];
  rows: CostDetailRow[];
  emptyBreakdown: string;
  emptyDetail: string;
  loading?: boolean;
  pageSize?: number;
  /** Optional per-row link target (e.g. Engineering drill-down). */
  drilldown?: (row: CostDetailRow) => string | undefined;
  /** This card's own filter control (rendered in the header). */
  filters?: ReactNode;
  /** This card's active-filter chips (rendered above the tab panel). */
  filterChips?: ReactNode;
}) {
  const [view, setView] = useState<"breakdown" | "detail">("breakdown");
  const [page, setPage] = useState(1);

  const pages = Math.max(1, Math.ceil(rows.length / pageSize));
  const current = Math.min(page, pages);
  const pageRows = rows.slice((current - 1) * pageSize, current * pageSize);

  const detail = rows.length ? (
    <>
      <TableWrap capped>
        <Table>
          <thead>
            <tr>
              {columns.map((label, index) => (
                <Th key={label} align={index === 0 ? "left" : "right"}>
                  {label}
                </Th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageRows.map((row) => {
              const href = drilldown?.(row);
              return (
                <Tr key={row.key}>
                  {row.cells.map((cell, index) => (
                    <Td
                      key={index}
                      align={index === 0 ? "left" : "right"}
                      className={index === 0 ? "table__cell--primary" : "num"}
                    >
                      {index === 0 && href ? <Link to={href}>{cell}</Link> : cell}
                    </Td>
                  ))}
                </Tr>
              );
            })}
          </tbody>
        </Table>
      </TableWrap>
      <Pagination
        page={current}
        pageSize={pageSize}
        total={rows.length}
        onPage={setPage}
        label="rows"
      />
    </>
  ) : (
    <EmptyState title={emptyDetail} />
  );

  const body = loading ? (
    <div className="stack" style={{ padding: 16 }}>
      <Skeleton width="80%" />
      <Skeleton width="60%" />
      <Skeleton width="70%" />
    </div>
  ) : rows.length ? (
    breakdown
  ) : (
    <EmptyState title={emptyBreakdown} />
  );

  return (
    <CardPanel title={title} subTitle={subTitle} extra={filters}>
      {filterChips}
      <Tabs
        tabs={[
          { id: "breakdown", label: "Breakdown" },
          { id: "detail", label: "Detail", counter: rows.length || undefined },
        ]}
        selected={view}
        onSelect={setView}
      >
        {view === "breakdown" ? body : detail}
      </Tabs>
    </CardPanel>
  );
}
