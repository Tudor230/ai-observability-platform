import { Button } from "./Button";
import { Select } from "./Inputs";

/**
 * Shared pager (extracted from Engineering, refinements v3): "Showing X–Y of Z"
 * with optional page-size control and Prev/Next. Server-side callers pass
 * `onPage`/`onPageSize`; client-side tables pass their own state setters.
 */
export function Pagination({
  page,
  pageSize,
  total,
  onPage,
  onPageSize,
  pageSizeOptions,
  label = "rows",
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (page: number) => void;
  onPageSize?: (pageSize: number) => void;
  pageSizeOptions?: number[];
  label?: string;
}) {
  if (total <= 0) return null;
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);

  return (
    <div
      className="row"
      style={{ justifyContent: "space-between", padding: 12, gap: 12, flexWrap: "wrap" }}
    >
      <span className="muted">
        Showing {from}–{to} of {total} {label}
      </span>
      <span className="row" style={{ gap: 8, alignItems: "center" }}>
        {onPageSize && pageSizeOptions?.length ? (
          <Select
            value={String(pageSize)}
            aria-label="Rows per page"
            onChange={(e) => onPageSize(Number(e.target.value))}
          >
            {pageSizeOptions.map((size) => (
              <option key={size} value={size}>
                {size} / page
              </option>
            ))}
          </Select>
        ) : null}
        <Button variant="quiet" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          Prev
        </Button>
        <Button variant="quiet" disabled={to >= total} onClick={() => onPage(page + 1)}>
          Next
        </Button>
      </span>
    </div>
  );
}
