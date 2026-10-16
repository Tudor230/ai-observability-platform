import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { BreakdownBars, type BreakdownRow } from "./charts/BreakdownBars";
import {
  CardPanel,
  EmptyState,
  Pagination,
  Skeleton,
  SortableTh,
  Table,
  TableWrap,
  Tabs,
  Td,
  Tr,
} from "./core";

export interface CostDetailRow {
  key: string;
  /** Detail columns; the first is the primary (left) cell. */
  cells: ReactNode[];
  /** Raw values parallel to `cells`; drives the detail table's column sort. */
  sortValues?: Array<string | number>;
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

type SortDirection = "asc" | "desc";

/** Numbers compare numerically; everything else sorts as case-insensitive text. */
function compareValues(
  a: string | number | undefined,
  b: string | number | undefined
): number {
  if (a === undefined || b === undefined) return 0;
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b), undefined, {
    numeric: true,
    sensitivity: "base",
  });
}

/**
 * Two-view cost card (refinements v3): a breakdown (bars) and a detail table
 * over the same rows, switched with `Tabs`. **Both** views share the same
 * *fixed* body height (`--card-scroll-height`) and render one page of rows that
 * fits inside it — nothing scrolls; the remainder is paginated.
 *
 * The detail table is sortable per column like the Engineering table: click a
 * header to sort descending, click it again to flip. Sorting is a detail-view
 * concern — the breakdown always keeps the incoming (cost-ranked) order — so
 * each view pages independently and switching tabs never resizes the card.
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
  pageSize = 6,
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
  const [breakdownPage, setBreakdownPage] = useState(1);
  const [detailPage, setDetailPage] = useState(1);
  const [detailSort, setDetailSort] = useState<{
    column: number;
    direction: SortDirection;
  } | null>(null);

  const detailRows = useMemo(() => {
    if (!detailSort) return rows;
    const sign = detailSort.direction === "asc" ? 1 : -1;
    // `sort` is stable, so ties keep the incoming cost ranking.
    return [...rows].sort(
      (a, b) =>
        sign *
        compareValues(a.sortValues?.[detailSort.column], b.sortValues?.[detailSort.column])
    );
  }, [rows, detailSort]);

  const toggleSort = (column: number) => {
    setDetailSort((prev) =>
      prev?.column === column
        ? { column, direction: prev.direction === "asc" ? "desc" : "asc" }
        : { column, direction: "desc" }
    );
    setDetailPage(1);
  };

  const pager = (page: number, onPage: (page: number) => void, total: number) => (
    <div className="card__pager">
      <Pagination page={page} pageSize={pageSize} total={total} onPage={onPage} label="rows" />
    </div>
  );

  const breakdownPages = Math.max(1, Math.ceil(rows.length / pageSize));
  const breakdownCurrent = Math.min(breakdownPage, breakdownPages);
  const visible = rows.slice((breakdownCurrent - 1) * pageSize, breakdownCurrent * pageSize);

  const detailPages = Math.max(1, Math.ceil(detailRows.length / pageSize));
  const detailCurrent = Math.min(detailPage, detailPages);
  const detailVisible = detailRows.slice(
    (detailCurrent - 1) * pageSize,
    detailCurrent * pageSize
  );

  const detail = rows.length ? (
    <>
      <TableWrap capped>
        <Table>
          <thead>
            <tr>
              {columns.map((label, index) => (
                <SortableTh
                  key={label}
                  sortKey={String(index)}
                  active={detailSort?.column === index}
                  direction={detailSort?.column === index ? detailSort.direction : "desc"}
                  onSort={(key) => toggleSort(Number(key))}
                  align={index === 0 ? "left" : "right"}
                >
                  {label}
                </SortableTh>
              ))}
            </tr>
          </thead>
          <tbody>
            {detailVisible.map((row) => (
              <Tr key={row.key}>
                {row.cells.map((cell, index) => (
                  <Td
                    key={index}
                    align={index === 0 ? "left" : "right"}
                    className={
                      index === 0 ? "table__cell--primary truncate" : "num"
                    }
                    title={index === 0 ? row.bar?.label ?? row.key : undefined}
                  >
                    {index === 0 && row.href ? <Link to={row.href}>{cell}</Link> : cell}
                  </Td>
                ))}
              </Tr>
            ))}
          </tbody>
        </Table>
      </TableWrap>
      {pager(detailCurrent, setDetailPage, detailRows.length)}
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
      {/* Same fixed body as the detail table; the pager stays outside, pinned
          to the bottom of the card in both views. */}
      <div className="card-scroll">{breakdown(visible)}</div>
      {pager(breakdownCurrent, setBreakdownPage, rows.length)}
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
