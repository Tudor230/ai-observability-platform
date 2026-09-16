import { Link } from "react-router-dom";

export interface BreakdownRow {
  key: string;
  label: string;
  value: number;
  valueLabel: string;
  sublabel?: string;
  href?: string;
}

/**
 * Horizontal bar breakdown — the readable "cost by X" list: label, bar
 * scaled to the largest value, and the formatted value on the right.
 */
export function BreakdownBars({ rows }: { rows: BreakdownRow[] }) {
  const max = rows.reduce((m, r) => Math.max(m, r.value), 0);
  return (
    <div className="breakdown">
      {rows.map((row) => {
        const width = max > 0 ? Math.max(2, (row.value / max) * 100) : 0;
        const label = row.href ? (
          <Link to={row.href} className="breakdown__label truncate" title={row.label}>
            {row.label}
          </Link>
        ) : (
          <span className="breakdown__label truncate" title={row.label}>
            {row.label}
          </span>
        );
        return (
          <div className="breakdown__row" key={row.key}>
            <div className="breakdown__top">
              {label}
              <span className="spacer" />
              <span className="num breakdown__value">{row.valueLabel}</span>
            </div>
            <div className="breakdown__track">
              <div className="breakdown__fill" style={{ width: `${width}%` }} />
            </div>
            {row.sublabel ? <div className="breakdown__sub">{row.sublabel}</div> : null}
          </div>
        );
      })}
    </div>
  );
}
