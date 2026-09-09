import { useOverview, useCosts, useMetrics } from "../api/hooks";
import { useFilters } from "../state/FiltersContext";
import { KpiCard } from "../components/KpiCard";
import { formatMoney, formatTokens } from "../lib/format";
import { buildForecast } from "../lib/forecast";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";

export default function Executive() {
  const { filters } = useFilters();
  const { data } = useOverview(filters);
  const { data: byService } = useCosts("client", filters);
  const { data: byModel } = useCosts("model", filters);
  const { data: ts } = useMetrics("total");

  const series = (ts?.items ?? []).map((m) => ({
    day: m.day,
    cost: m.total_cost,
    tokens: m.total_tokens,
  }));
  const forecast = buildForecast(series, 7);

  const execs = data?.executions ?? 0;
  const avgPerExec = execs ? (data?.total_cost ?? 0) / execs : null;
  const tokens = data?.total_tokens ?? 0;
  const costPerToken = tokens ? (data?.total_cost ?? 0) / tokens : null;
  const forecastTotal = forecast.reduce((s, p) => s + p.cost, 0);

  return (
    <div className="grid" style={{ gap: 16 }}>
      <div className="grid grid-4">
        <KpiCard label="Total AI cost" value={formatMoney(data?.total_cost)} />
        <KpiCard label="Cost per execution" value={formatMoney(avgPerExec)} />
        <KpiCard label="Cost per 1k tokens" value={costPerToken === null ? "—" : formatMoney(costPerToken * 1000)} />
        <KpiCard label="Total tokens" value={formatTokens(tokens)} />
      </div>

      {forecast.length > 0 && (
        <div className="panel">
          <h3>Forecast (next 7 days, linear projection — estimate)</h3>
          <p className="muted">
            Projected spend: <strong>{formatMoney(forecastTotal)}</strong> over the next {forecast.length} days.
          </p>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={[...series.slice(-14), ...forecast]}>
              <CartesianGrid stroke="#2a2f3a" strokeDasharray="3 3" />
              <XAxis dataKey="day" stroke="#9aa3b2" />
              <YAxis stroke="#9aa3b2" />
              <Tooltip contentStyle={{ background: "#171a21", border: "1px solid #2a2f3a" }} />
              <Line type="monotone" dataKey="cost" stroke="#4f8cff" dot={false} strokeDasharray="5 4" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="panel">
        <h3>Cost per client (service)</h3>
        <table>
          <thead>
            <tr><th>Client</th><th>Cost</th><th>Executions</th><th>LLM calls</th></tr>
          </thead>
          <tbody>
            {(byService?.items ?? []).map((c) => (
              <tr key={c.key}>
                <td>{c.key}</td>
                <td>{formatMoney(c.total_cost)}</td>
                <td>{c.executions}</td>
                <td>{c.llm_calls}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel">
        <h3>Cost by model</h3>
        <table>
          <thead>
            <tr><th>Provider / model</th><th>Cost</th><th>Input tokens</th><th>Output tokens</th></tr>
          </thead>
          <tbody>
            {(byModel?.items ?? []).map((m) => (
              <tr key={m.key}>
                <td>{m.provider} · {m.model}</td>
                <td>{formatMoney(m.total_cost)}</td>
                <td>{m.input_tokens}</td>
                <td>{m.output_tokens}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel">
        <h3>Cost trend</h3>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={series}>
            <CartesianGrid stroke="#2a2f3a" strokeDasharray="3 3" />
            <XAxis dataKey="day" stroke="#9aa3b2" />
            <YAxis stroke="#9aa3b2" />
            <Tooltip contentStyle={{ background: "#171a21", border: "1px solid #2a2f3a" }} />
            <Line type="monotone" dataKey="cost" stroke="#4f8cff" name="Cost" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
