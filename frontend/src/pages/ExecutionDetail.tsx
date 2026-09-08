import { useParams, Link } from "react-router-dom";
import { useExecution, useSpans, useFailures } from "../api/hooks";
import { KpiCard } from "../components/KpiCard";
import { formatMoney, formatTokens, formatMs } from "../lib/format";
import type { Span, FailureNode } from "../api/types";

export default function ExecutionDetail() {
  const { id = "" } = useParams();
  const { data: ex, isLoading: l1 } = useExecution(id);
  const { data: spansData } = useSpans(id);
  const { data: failures } = useFailures(id);

  if (l1) return <p className="muted">Loading…</p>;
  if (!ex) return <p className="error">Execution not found.</p>;

  const spans = spansData?.items ?? [];

  return (
    <div className="grid" style={{ gap: 16 }}>
      <div className="row">
        <Link to="/engineering" className="muted">← back</Link>
        <h2 style={{ margin: 0 }}>
          {ex.workflow ?? ex.trace_id}{" "}
          <span className={`status status-${ex.status}`}>{ex.status}</span>
        </h2>
        <span className="spacer" />
        <span className="muted">trace {ex.trace_id}</span>
      </div>

      <div className="grid grid-4">
        <KpiCard label="Cost" value={formatMoney(ex.total_cost)} tone={ex.error_kind ? "bad" : undefined} />
        <KpiCard label="Tokens" value={formatTokens(ex.total_tokens)} sub={`${ex.input_tokens} in / ${ex.output_tokens} out`} />
        <KpiCard label="Duration" value={formatMs(ex.duration_ms)} />
        <KpiCard label="Calls" value={`${ex.llm_calls} LLM / ${ex.tool_calls} tool`} sub={`${ex.retrieval_calls} retrieval, ${ex.agent_calls} agent`} />
        <KpiCard label="Errors" value={ex.error_count} tone={ex.error_count ? "bad" : undefined} />
        <KpiCard label="Retries" value={ex.retry_count} />
      </div>

      {ex.metadata && (
        <div className="panel">
          <h3>Business context</h3>
          <pre style={{ margin: 0 }}>{JSON.stringify(ex.metadata, null, 2)}</pre>
        </div>
      )}

      {failures && failures.error_count > 0 && (
        <div className="panel">
          <h3>Failure tree ({failures.error_count})</h3>
          <FailureTree nodes={failures.nodes} />
        </div>
      )}

      <div className="panel">
        <h3>Span tree ({spans.length})</h3>
        <SpanTree spans={spans} />
      </div>
    </div>
  );
}

function SpanTree({ spans }: { spans: Span[] }) {
  const childrenOf = new Map<string | null, Span[]>();
  for (const s of spans) {
    const p = s.parent_id ?? null;
    if (!childrenOf.has(p)) childrenOf.set(p, []);
    childrenOf.get(p)!.push(s);
  }
  const render = (id: string | null, depth: number): React.ReactNode => {
    const kids = childrenOf.get(id) ?? [];
    return kids.map((s) => (
      <div key={s.span_id}>
        <div className={`tree-row ${s.status === "error" ? "error" : ""}`} style={{ paddingLeft: depth * 18 }}>
          <span className="badge badge-kind">{s.kind}</span>{" "}
          <span>{s.name ?? s.span_id}</span>
          {s.llm_model && <span className="muted"> · {s.llm_model}</span>}
          <span className="muted"> · {formatMs(s.duration_ms)}</span>
          {s.total_tokens > 0 && <span className="muted"> · {formatTokens(s.total_tokens)} tok</span>}
          {s.error_kind && <span className="error"> · {s.error_kind}</span>}
        </div>
        {render(s.span_id, depth + 1)}
      </div>
    ));
  };
  return <div className="tree">{render(null, 0)}</div>;
}

function FailureTree({ nodes }: { nodes: FailureNode[] }) {
  if (!nodes.length) return <p className="muted">No failures.</p>;
  return (
    <div className="tree">
      {nodes.map((n) => (
        <div key={n.span_id} className="tree-row error">
          <span className="badge badge-kind">{n.kind}</span>{" "}
          <span>{n.name ?? n.span_id}</span>
          {n.error_kind && <span className="error"> · {n.error_kind}</span>}
          {n.error_message && <span className="muted"> — {n.error_message}</span>}
        </div>
      ))}
    </div>
  );
}
