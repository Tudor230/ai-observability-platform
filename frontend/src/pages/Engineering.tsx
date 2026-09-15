import { Link } from "react-router-dom";
import { useExecutions } from "../api/hooks";
import { useFilters } from "../state/FiltersContext";
import { QueryError } from "../components/QueryError";
import { formatMoney, formatTokens, formatMs } from "../lib/format";

export default function Engineering() {
  const { filters } = useFilters();
  const { data, isLoading, isError, error } = useExecutions(filters);

  return (
    <div className="panel">
      <h3>Trace Explorer</h3>
      {isError ? (
        <QueryError what="executions" error={error} />
      ) : isLoading ? (
        <p className="muted">Loading…</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Workflow</th>
              <th>Client</th>
              <th>Status</th>
              <th>Error</th>
              <th>Duration</th>
              <th>Tokens</th>
              <th>Cost</th>
              <th>Started</th>
            </tr>
          </thead>
          <tbody>
            {(data?.items ?? []).map((e) => (
              <tr key={e.id}>
                <td>
                  <Link to={`/engineering/${e.id}`}>{e.workflow ?? e.trace_id}</Link>
                </td>
                <td>{e.client_id ?? "—"}</td>
                <td>
                  <span className={`status status-${e.status}`}>{e.status}</span>
                </td>
                <td>{e.error_kind ?? "—"}</td>
                <td>{formatMs(e.duration_ms)}</td>
                <td>{formatTokens(e.total_tokens)}</td>
                <td>{formatMoney(e.total_cost)}</td>
                <td className="muted">{e.started_at ? new Date(e.started_at).toLocaleString() : "—"}</td>
              </tr>
            ))}
            {!data?.items?.length && (
              <tr>
                <td colSpan={8} className="muted">
                  No executions in range.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    </div>
  );
}
