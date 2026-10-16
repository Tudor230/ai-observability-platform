import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { BreakdownBars, type BreakdownRow } from "./charts/BreakdownBars";
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
} from "./core";

export interface CostDetailRow {
  key: string;
  /** Detail columns; the first is the primary (left) cell. */
  cells: ReactNode[];
  /** Detail-view link target; the breakdown bars link to the same place. */
  href?: string;
  /** Breakdown-bar inputs for this row (label falls back to the key). */
  bar?: BreakdownBarInput;
}

export interface BreakdownBarInput {
  label: string;
  value: number;
  valueLabel: string;
  sublabel?: string;
}

/**
 * Two-view cost card (refinements v3): a breakdown (bars) and a detail table
 * over the same rows, switched with `Tabs`. **Both** views render one page of
 * rows and share the same *fixed* body height (`--card-scroll-height`, sticky
 * header, scroll inside), so switching tabs never resizes the card, and both
 * paginate client-side at `pageSize` (10 by default) — the breakdown is a
 * readable top-N list rather than an unbounded wall of bars.
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
  filters,
  filterChips,
}: {
  title: string;
  subTitle?: string;
  /** Renders the current page of bars (receives only the visible rows). */
  breakdown: (visible: CostDetailRow[]) => ReactNode;
  /** Detail header labels; the first column is the primary (left) one. */
  columns: string[];
  rows: CostDetailRow[];
  emptyBreakdown: string;
  emptyDetail: string;
  loading?: boolean;
  pageSize?: number;
  /** This card's own filter control (rendered in the header). */
  filters?: ReactNode;
  /** This card's active-filter chips (rendered above the tab panel). */
  filterChips?: ReactNode;
}) {
  const [view, setView] = useState<"breakdown" | "detail">("breakdown");
  const [page, setPage] = useState(1);

  const pages = Math.max(1, Math.ceil(rows.length / pageSize));
  const current = Math.min(page, pages);
  const visible = rows.slice((current - 1) * pageSize, current * pageSize);

  const pager = (
    <div className="card__pager">
      <Pagination
        page={current}
        pageSize={pageSize}
        total={rows.length}
        onPage={setPage}
        label="rows"
      />
    </div>
  );

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
            {visible.map((row) => (
              <Tr key={row.key}>
                {row.cells.map((cell, index) => (
                  <Td
                    key={index}
                    align={index === 0 ? "left" : "right"}
                    className={index === 0 ? "table__cell--primary" : "num"}
                  >
                    {index === 0 && row.href ? <Link to={row.href}>{cell}</Link> : cell}
                  </Td>
                ))}
              </Tr>
            ))}
          </tbody>
        </Table>
      </TableWrap>
      {pager}
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
    <>
      {/* Same cap/scroll as the detail table; the pager stays outside, pinned
          to the bottom of the card in both views. */}
      <div className="card-scroll">{breakdown(visible)}</div>
      {pager}
    </>
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

/** Shared breakdown renderer: maps the visible rows onto `BreakdownBars`. */
export function CostCardBars({
  rows,
  ariaLabel,
}: {
  rows: CostDetailRow[];
  ariaLabel?: string;
}) {
  const bars: BreakdownRow[] = rows.map((row) => ({
    key: row.key,
    label: row.bar?.label ?? row.key,
    value: row.bar?.value ?? 0,
    valueLabel: row.bar?.valueLabel ?? "",
    sublabel: row.bar?.sublabel,
    href: row.href,
  }));
  return (
    <div style={{ padding: "var(--global-dimension-size-100)" }}>
      <BreakdownBars rows={bars} ariaLabel={ariaLabel} />
    </div>
  );
}
