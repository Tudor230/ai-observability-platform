export function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const v = Number(value);
  if (!Number.isFinite(v)) return "—";
  const abs = Math.abs(v);
  // Sub-cent amounts (LLM calls) keep precision; normal amounts get grouping.
  if (abs > 0 && abs < 0.01) {
    return `$${v.toFixed(6).replace(/0+$/, "").replace(/\.$/, "")}`;
  }
  return `$${v.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

/**
 * Unit costs (per 1M tokens, per execution) are far smaller than the totals
 * `formatMoney` was built for — it rounds to cents above $0.01 and would render
 * $0.0294 as "$0.03". Unit costs keep four decimals instead.
 */
export function formatUnitCost(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const v = Number(value);
  if (!Number.isFinite(v)) return "—";
  const abs = Math.abs(v);
  return `$${v.toFixed(abs > 0 && abs < 0.0001 ? 6 : 4)}`;
}

export function formatTokens(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return String(value);
}

export function formatMs(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (value >= 1000) return `${(value / 1000).toFixed(2)}s`;
  return `${value.toFixed(0)}ms`;
}

export function formatPct(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  return isNaN(d.getTime()) ? value : d.toLocaleString();
}
