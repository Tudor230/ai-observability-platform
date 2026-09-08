import { useOverview, useMetrics } from "../api/hooks";
import { useFilters } from "../state/FiltersContext";
import { KpiCard } from "../components/KpiCard";
import { formatMoney, formatTokens, formatMs, formatPct } from "../lib/format";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";

export default function Overview() {
  const { filters } = useFilters();
  const { data, isLoading } = useOverview(filters);
  const { data: ts } = useMetrics("total");

  const series = (ts?.items ?? []).map((m) => ({
    day: m.day.slice(5),
    cost: m.total_cost,
    executions: m.executions,
    tokens: m.total_tokens,
  }));

  return (
    <div className="grid" style={{ gap: 16 }}>
      {isLoading ? (
        <p className="muted">Loading…</p>
      ) : (
        <>
          <div className="grid grid-4">
            <KpiCard
              label="Total cost"
              value={formatMoney(data?.total_cost)}
              sub={delta(data?.deltas?.total_cost_pct)}
              tone={data && data.deltas?.total_cost_pct ? "bad" : undefined}
            />
            <KpiCard label="Executions" value={data?.executions ?? 0} sub={delta(data?.deltas?.executions_pct)} />
            <KpiCard
              label="Error rate"
              value={formatPct(data?.error_rate)}
              sub={delta(data?.deltas?.error_rate_pct)}
              tone={data && data.error_rate ? "bad" : undefined}
            />
            <KpiCard label="Total tokens" value={formatTokens(data?.total_tokens)} />
            <KpiCard label="LLM calls" value={data?.llm_calls ?? 0} />
            <KpiCard label="Tool calls" value={data?.tool_calls ?? 0} />
            <KpiCard label="Avg duration" value={formatMs(data?.avg_duration_ms)} />
            <KpiCard label="Open alerts" value={data?.open_alerts ?? 0} tone="warn" />
          </div>

          <div className="panel">
            <h3>Cost over time</h3>
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={series}>
                <defs>
                  <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#4f8cff" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="#4f8cff" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#2a2f3a" strokeDasharray="3 3" />
                <XAxis dataKey="day" stroke="#9aa3b2" />
                <YAxis stroke="#9aa3b2" />
                <Tooltip contentStyle={{ background: "#171a21", border: "1px solid #2a2f3a" }} />
                <Area type="monotone" dataKey="cost" stroke="#4f8cff" fill="url(#g)" name="Cost" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </div>
  );
}

function delta(pct: number | null | undefined) {
  if (pct === null || pct === undefined) return null;
  const sign = pct >= 0 ? "+" : "";
  return <span className={pct >= 0 ? "error" : "muted"}>{sign}{pct.toFixed(1)}% vs prev</span>;
}
