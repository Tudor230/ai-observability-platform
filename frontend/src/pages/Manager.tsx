import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Cell,
} from "recharts";
import { useCosts, useWorkflows, useClients, useAgents, useAlerts, useMetrics, useBudgetStatus } from "../api/hooks";
import { useFilters } from "../state/FiltersContext";
import { QueryError } from "../components/QueryError";
import { formatMoney, formatPct } from "../lib/format";

const BAR_COLORS = ["#4f8cff", "#2ecc71", "#f5b041", "#e74c3c", "#9b59b6", "#1abc9c"];

export default function Manager() {
  const { filters } = useFilters();
  const costWf = useCosts("workflow", filters);
  const costClient = useCosts("client", filters);
  const workflows = useWorkflows(filters);
  const clients = useClients(filters);
  const { data: costByWf } = costWf;
  const { data: costByClient } = costClient;
  const { data: workflowsData } = workflows;
  const { data: clientsData } = clients;
  const { data: agents } = useAgents(filters);
  const { data: alerts } = useAlerts();
  const { data: trends } = useMetrics("total", filters);
  const { data: budgets } = useBudgetStatus();
  const chartError =
    costWf.error ?? costClient.error ?? workflows.error ?? clients.error;

  return (
    <div className="grid" style={{ gap: 16 }}>
      {(costWf.isError || costClient.isError || workflows.isError || clients.isError) && (
        <QueryError what="manager data" error={chartError} />
      )}
      <div className="grid grid-2">
        <Chart title="Cost by workflow" rows={(costByWf?.items ?? []).map((i) => ({ name: i.key, cost: i.total_cost ?? 0 }))} />
        <Chart title="Cost by client" rows={(costByClient?.items ?? []).map((i) => ({ name: i.key, cost: i.total_cost ?? 0 }))} />
      </div>

      <div className="grid grid-2">
        <div className="panel">
          <h3>Workflows</h3>
          <table>
            <thead>
              <tr><th>Workflow</th><th>Exec</th><th>Err</th><th>Cost</th></tr>
            </thead>
            <tbody>
              {(workflowsData?.items ?? []).map((w) => (
                <tr key={w.name}>
                  <td>{w.name}</td>
                  <td>{w.executions}</td>
                  <td className={w.error_rate ? "error" : ""}>{formatPct(w.error_rate)}</td>
                  <td>{formatMoney(w.total_cost)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="panel">
          <h3>Clients</h3>
          <table>
            <thead>
              <tr><th>Client</th><th>Exec</th><th>Cost</th><th>Tokens</th></tr>
            </thead>
            <tbody>
              {(clientsData?.items ?? []).map((c) => (
                <tr key={c.client_id}>
                  <td>{c.client_id}</td>
                  <td>{c.executions}</td>
                  <td>{formatMoney(c.total_cost)}</td>
                  <td>{c.total_tokens}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel">
        <h3>Agent efficiency</h3>
        <table>
          <thead>
            <tr><th>Agent</th><th>Exec</th><th>Err</th><th>Cost</th><th>Tokens</th></tr>
          </thead>
          <tbody>
            {(agents?.items ?? []).map((a) => (
              <tr key={a.name}>
                <td>{a.name}</td>
                <td>{a.executions}</td>
                <td className={a.error_rate ? "error" : ""}>{formatPct(a.error_rate)}</td>
                <td>{formatMoney(a.total_cost)}</td>
                <td>{a.total_tokens}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!agents?.items?.length && <p className="muted">No agent spans seen yet.</p>}
      </div>

      <div className="panel">
        <h3>Open alerts ({alerts?.total ?? 0})</h3>
        {(alerts?.items ?? []).map((a) => (
          <div key={a.id} className={`row alert-${a.severity}`} style={{ padding: "8px 4px", borderBottom: "1px solid var(--border)" }}>
            <span className="badge">{a.severity}</span>
            <span>{a.message}</span>
            <span className="spacer" />
            <span className="muted">{a.triggered_at ? new Date(a.triggered_at).toLocaleString() : ""}</span>
          </div>
        ))}
        {!alerts?.items?.length && <p className="muted">No open alerts.</p>}
      </div>

      <div className="panel">
        <h3>Budgets ({budgets?.total ?? 0})</h3>
        {(budgets?.items ?? []).map((b) => {
          const pct = Math.round(b.utilization * 100);
          const barPct = Math.min(100, pct); // clamp only the bar, never the number (F23)
          const over = b.utilization >= 1;
          return (
            <div key={b.id} style={{ padding: "8px 4px", borderBottom: "1px solid var(--border)" }}>
              <div className="row">
                <span>{b.name ?? `Budget ${b.period}`}{b.period_type ? ` (${b.period_type})` : ""}</span>
                <span className="spacer" />
                <span className="muted">
                  {formatMoney(b.spend)} / {formatMoney(b.amount)} · {pct}%
                </span>
              </div>
              <div style={{ background: "var(--panel-2)", borderRadius: 6, height: 8, marginTop: 6 }}>
                <div
                  style={{
                    width: `${barPct}%`,
                    height: 8,
                    borderRadius: 6,
                    background: over ? "var(--bad)" : pct >= 80 ? "var(--warn)" : "var(--ok)",
                  }}
                />
              </div>
            </div>
          );
        })}
        {!budgets?.items?.length && <p className="muted">No budgets configured.</p>}
      </div>

      <TrendChart data={trends?.items ?? []} />
    </div>
  );
}

function Chart({ title, rows }: { title: string; rows: { name?: string; cost: number }[] }) {
  return (
    <div className="panel">
      <h3>{title}</h3>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={rows}>
          <CartesianGrid stroke="#2a2f3a" strokeDasharray="3 3" />
          <XAxis dataKey="name" stroke="#9aa3b2" interval={0} />
          <YAxis stroke="#9aa3b2" />
          <Tooltip contentStyle={{ background: "#171a21", border: "1px solid #2a2f3a" }} />
          <Bar dataKey="cost" radius={[4, 4, 0, 0]}>
            {rows.map((_, i) => (
              <Cell key={i} fill={BAR_COLORS[i % BAR_COLORS.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function TrendChart({ data }: { data: { day: string; total_cost: number }[] }) {
  const series = data.map((m) => ({ day: m.day.slice(5), cost: m.total_cost }));
  return (
    <div className="panel">
      <h3>Consumption trend (cost)</h3>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={series}>
          <CartesianGrid stroke="#2a2f3a" strokeDasharray="3 3" />
          <XAxis dataKey="day" stroke="#9aa3b2" />
          <YAxis stroke="#9aa3b2" />
          <Tooltip contentStyle={{ background: "#171a21", border: "1px solid #2a2f3a" }} />
          <Bar dataKey="cost" fill="#4f8cff" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
