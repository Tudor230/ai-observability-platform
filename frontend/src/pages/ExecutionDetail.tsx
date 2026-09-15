import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useExecution, useFailures, useSpans } from "../api/hooks";
import { PageHeader } from "../components/PageHeader";
import { RefreshButton } from "../components/RefreshButton";
import { KindBadge, KindIcon, StatusBadge } from "../components/domain";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardPanel,
  EmptyState,
  Metric,
  QueryError,
  Skeleton,
  Table,
  TableWrap,
  Tabs,
  Td,
  Th,
  Tr,
} from "../components/core";
import { IconArrowLeft } from "../components/core/icons";
import { formatMoney, formatMs, formatTokens } from "../lib/format";
import type { FailureNode, Span } from "../api/types";

type TabId = "spans" | "failures" | "metadata";

interface SpanNode {
  span: Span;
  depth: number;
}

function buildTree(spans: Span[]): SpanNode[] {
  const byParent = new Map<string | null, Span[]>();
  const ids = new Set(spans.map((s) => s.span_id));
  for (const span of spans) {
    const parent = span.parent_id && ids.has(span.parent_id) ? span.parent_id : null;
    const list = byParent.get(parent) ?? [];
    list.push(span);
    byParent.set(parent, list);
  }
  for (const list of byParent.values()) {
    list.sort((a, b) => {
      const at = a.started_at ? Date.parse(a.started_at) : 0;
      const bt = b.started_at ? Date.parse(b.started_at) : 0;
      return at - bt;
    });
  }
  const out: SpanNode[] = [];
  const walk = (parent: string | null, depth: number) => {
    for (const span of byParent.get(parent) ?? []) {
      out.push({ span, depth });
      walk(span.span_id, depth + 1);
    }
  };
  walk(null, 0);
  return out;
}

function timeRange(nodes: SpanNode[]): { start: number; total: number } {
  const starts: number[] = [];
  const ends: number[] = [];
  for (const { span } of nodes) {
    const start = span.started_at ? Date.parse(span.started_at) : NaN;
    if (Number.isFinite(start)) {
      starts.push(start);
      ends.push(start + (span.duration_ms ?? 0));
    }
  }
  if (!starts.length) {
    const maxDuration = Math.max(...nodes.map((n) => n.span.duration_ms ?? 0), 1);
    return { start: 0, total: maxDuration };
  }
  const start = Math.min(...starts);
  const end = Math.max(...ends, start + 1);
  return { start, total: end - start };
}

export default function ExecutionDetail() {
  const { id = "" } = useParams();
  const execution = useExecution(id);
  const spans = useSpans(id);
  const failures = useFailures(id);
  const [tab, setTab] = useState<TabId>("spans");
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);

  const ex = execution.data;
  const spanItems = useMemo(() => spans.data?.items ?? [], [spans.data]);
  const nodes = useMemo(() => buildTree(spanItems), [spanItems]);
  const range = useMemo(() => timeRange(nodes), [nodes]);

  const selectedSpan = spanItems.find((s) => s.span_id === selectedSpanId) ?? null;
  const failureNodes = failures.data?.nodes ?? [];

  if (execution.isLoading) {
    return (
      <div className="page">
        <Skeleton shape="title" width={280} />
        <div className="grid grid-4">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} shape="chart" />
          ))}
        </div>
        <Skeleton shape="chart" />
      </div>
    );
  }

  if (execution.isError) {
    const message = execution.error instanceof Error ? execution.error.message : "";
    const notFound = message.includes("404");
    return (
      <div className="page">
        <PageHeader title="Execution" />
        <Alert
          variant="danger"
          message={notFound ? "Execution not found." : "Failed to load the execution."}
          detail={notFound ? `No execution with id ${id}.` : message}
          extra={
            <Link to="/engineering" className="button" data-size="S">
              Back to traces
            </Link>
          }
        />
      </div>
    );
  }

  if (!ex) return null;

  return (
    <div className="page">
      <PageHeader
        title={
          <span className="row" style={{ minWidth: 0 }}>
            <span className="truncate">{ex.workflow ?? ex.trace_id}</span>
            <StatusBadge status={ex.status} />
          </span>
        }
        subTitle={
          <span className="row row--wrap" style={{ gap: 8 }}>
            <span className="inline-code">{ex.trace_id}</span>
            {ex.client_id ? <span>client {ex.client_id}</span> : null}
            {ex.project_id ? <span>· project {ex.project_id}</span> : null}
            {ex.workflow_version ? <span>· v{ex.workflow_version}</span> : null}
          </span>
        }
        extra={
          <>
            <Button variant="quiet" onClick={() => history.back()} title="Back">
              <IconArrowLeft size={14} />
              Back
            </Button>
            <RefreshButton />
          </>
        }
      />

      <div className="grid grid-4">
        <Metric
          label="Cost"
          value={formatMoney(ex.total_cost)}
          sub={
            !ex.cost_complete && ex.unpriced_calls > 0 ? (
              <Badge variant="warning">{ex.unpriced_calls} unpriced</Badge>
            ) : (
              "fully priced"
            )
          }
        />
        <Metric
          label="Tokens"
          value={formatTokens(ex.total_tokens)}
          sub={`${formatTokens(ex.input_tokens)} in / ${formatTokens(ex.output_tokens)} out`}
        />
        <Metric label="Duration" value={formatMs(ex.duration_ms)} />
        <Metric
          label="Calls"
          value={`${ex.llm_calls} LLM · ${ex.tool_calls} tool`}
          sub={`${ex.retrieval_calls} retrieval · ${ex.agent_calls} agent`}
        />
        <Metric
          label="Errors"
          value={ex.error_count}
          tone={ex.error_count > 0 ? "danger" : "default"}
          sub={ex.error_kind ?? "none"}
        />
        <Metric label="Retries" value={ex.retry_count} />
      </div>

      <CardPanel title="Trace" subTitle={`${spanItems.length} spans`}>
        <Tabs
          tabs={[
            { id: "spans", label: "Spans", counter: spanItems.length },
            { id: "failures", label: "Failures", counter: failureNodes.length },
            { id: "metadata", label: "Business context" },
          ]}
          selected={tab}
          onSelect={setTab}
        >
          {tab === "spans" ? (
            spans.isError ? (
              <div style={{ padding: 16 }}>
                <QueryError what="spans" error={spans.error} />
              </div>
            ) : spans.isLoading ? (
              <div className="stack" style={{ padding: 16 }}>
                {Array.from({ length: 8 }, (_, i) => (
                  <Skeleton key={i} shape="text" width="100%" />
                ))}
              </div>
            ) : (
              <div className="split" style={{ padding: "var(--global-dimension-size-200)" }}>
                <SpanTree
                  nodes={nodes}
                  range={range}
                  selectedSpanId={selectedSpanId}
                  onSelect={setSelectedSpanId}
                />
                <Card titleSeparator={false}>
                  <CardHeader title="Span detail" />
                  <CardBody>
                    <SpanDetail span={selectedSpan} />
                  </CardBody>
                </Card>
              </div>
            )
          ) : null}

          {tab === "failures" ? (
            failures.isError ? (
              <div style={{ padding: 16 }}>
                <QueryError what="the failure tree" error={failures.error} />
              </div>
            ) : failureNodes.length ? (
              <FailureTree nodes={failureNodes} />
            ) : (
              <EmptyState
                title="No classified failures"
                description="Every span in this execution completed without an error classification."
              />
            )
          ) : null}

          {tab === "metadata" ? (
            ex.metadata && Object.keys(ex.metadata).length ? (
              <div style={{ padding: "var(--global-dimension-size-200)" }}>
                <pre className="code-block">{JSON.stringify(ex.metadata, null, 2)}</pre>
              </div>
            ) : (
              <EmptyState
                title="No business context"
                description="The SDK did not attach business metadata to this workflow root."
              />
            )
          ) : null}
        </Tabs>
      </CardPanel>
    </div>
  );
}

function SpanTree({
  nodes,
  range,
  selectedSpanId,
  onSelect,
}: {
  nodes: SpanNode[];
  range: { start: number; total: number };
  selectedSpanId: string | null;
  onSelect: (id: string) => void;
}) {
  if (!nodes.length) {
    return <EmptyState title="No spans" description="This execution has no normalized spans." />;
  }
  return (
    <div className="card" style={{ minWidth: 0 }}>
      <div className="trace-tree">
        <div className="trace-tree__header">
          <span>Span</span>
          <span>Timeline</span>
        </div>
        <div className="trace-tree__rows">
          {nodes.map(({ span, depth }) => {
            const start = span.started_at ? Date.parse(span.started_at) : range.start;
            const left = ((start - range.start) / range.total) * 100;
            const width = ((span.duration_ms ?? 0) / range.total) * 100;
            return (
              <button
                type="button"
                key={span.span_id}
                className="span-row"
                data-selected={span.span_id === selectedSpanId}
                onClick={() => onSelect(span.span_id)}
              >
                <span className="span-row__name">
                  <span
                    className="span-row__indent"
                    style={{ paddingLeft: depth * 14 }}
                    aria-hidden="true"
                  >
                    {depth > 0 ? "└" : ""}
                  </span>
                  <KindBadge kind={span.kind} />
                  <span className="span-row__label" title={span.name ?? span.span_id}>
                    {span.name ?? span.span_id}
                  </span>
                  {span.llm_model ? (
                    <span className="span-row__meta">{span.llm_model}</span>
                  ) : null}
                </span>
                <span className="span-row__waterfall">
                  <span
                    className="span-row__bar"
                    data-kind={span.kind}
                    data-status={span.status}
                    style={{
                      left: `${Math.min(99, Math.max(0, left))}%`,
                      width: `${Math.min(100, Math.max(0.5, width))}%`,
                    }}
                    title={`${formatMs(span.duration_ms)}`}
                  />
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function SpanDetail({ span }: { span: Span | null }) {
  if (!span) {
    return (
      <EmptyState
        title="Select a span"
        description="Pick a row in the trace tree to inspect its inputs, tokens and attributes."
      />
    );
  }
  return (
    <div className="span-detail">
      <div className="row row--wrap">
        <KindIcon kind={span.kind} size={16} />
        <strong className="truncate">{span.name ?? span.span_id}</strong>
        <StatusBadge status={span.status} />
      </div>

      <div className="grid grid-3" style={{ gap: 12 }}>
        <div>
          <div className="span-detail__section-title">Duration</div>
          <div>{formatMs(span.duration_ms)}</div>
        </div>
        <div>
          <div className="span-detail__section-title">Tokens</div>
          <div>
            {formatTokens(span.total_tokens)}
            <span className="muted" style={{ fontSize: 12 }}>
              {" "}
              ({formatTokens(span.input_tokens)} in / {formatTokens(span.output_tokens)} out)
            </span>
          </div>
        </div>
        <div>
          <div className="span-detail__section-title">Cost</div>
          <div>{formatMoney(span.cost)}</div>
        </div>
      </div>

      <div>
        <div className="span-detail__section-title">Details</div>
        <div className="kv">
          <span className="kv__key">Span id</span>
          <span className="kv__value inline-code">{span.span_id}</span>
          {span.parent_id ? (
            <>
              <span className="kv__key">Parent</span>
              <span className="kv__value inline-code">{span.parent_id}</span>
            </>
          ) : null}
          {span.llm_model ? (
            <>
              <span className="kv__key">Model</span>
              <span className="kv__value">
                {span.llm_provider ? `${span.llm_provider} · ` : ""}
                {span.llm_model}
              </span>
            </>
          ) : null}
          {span.tool_name ? (
            <>
              <span className="kv__key">Tool</span>
              <span className="kv__value">{span.tool_name}</span>
            </>
          ) : null}
          {span.retrieval_doc_count !== null ? (
            <>
              <span className="kv__key">Retrieved documents</span>
              <span className="kv__value">{span.retrieval_doc_count}</span>
            </>
          ) : null}
          {span.retry_count > 0 ? (
            <>
              <span className="kv__key">Retries</span>
              <span className="kv__value">{span.retry_count}</span>
            </>
          ) : null}
          {span.error_kind ? (
            <>
              <span className="kv__key">Failure kind</span>
              <span className="kv__value text-danger">{span.error_kind}</span>
            </>
          ) : null}
          {span.error_message ? (
            <>
              <span className="kv__key">Error</span>
              <span className="kv__value text-danger">{span.error_message}</span>
            </>
          ) : null}
          <span className="kv__key">Started</span>
          <span className="kv__value num">
            {span.started_at ? new Date(span.started_at).toLocaleString() : "—"}
          </span>
        </div>
      </div>

      {span.attributes && Object.keys(span.attributes).length ? (
        <div>
          <div className="span-detail__section-title">Attributes</div>
          <pre className="code-block">{JSON.stringify(span.attributes, null, 2)}</pre>
        </div>
      ) : null}
    </div>
  );
}

function FailureTree({ nodes }: { nodes: FailureNode[] }) {
  const byId = new Map(nodes.map((n) => [n.span_id, n]));
  const children = new Map<string | null, FailureNode[]>();
  for (const node of nodes) {
    const parent = node.parent_id && byId.has(node.parent_id) ? node.parent_id : null;
    const list = children.get(parent) ?? [];
    list.push(node);
    children.set(parent, list);
  }

  const rows: { node: FailureNode; depth: number }[] = [];
  const walk = (parent: string | null, depth: number) => {
    for (const node of children.get(parent) ?? []) {
      rows.push({ node, depth });
      walk(node.span_id, depth + 1);
    }
  };
  walk(null, 0);

  return (
    <TableWrap>
      <Table>
        <thead>
          <tr>
            <Th>Span</Th>
            <Th>Kind</Th>
            <Th>Failure kind</Th>
            <Th>Error type</Th>
            <Th>Message</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ node, depth }) => (
            <Tr key={node.span_id}>
              <Td>
                <span style={{ paddingLeft: depth * 16 }} className="row">
                  <KindIcon kind={node.kind} size={13} />
                  <span className="truncate">{node.name ?? node.span_id}</span>
                </span>
              </Td>
              <Td>
                <KindBadge kind={node.kind} />
              </Td>
              <Td>
                <Badge variant="danger">{node.error_kind ?? "error"}</Badge>
              </Td>
              <Td className="muted">{node.error_type ?? "—"}</Td>
              <Td className="muted" style={{ maxWidth: 420 }}>
                {node.error_message ?? "—"}
              </Td>
            </Tr>
          ))}
        </tbody>
      </Table>
    </TableWrap>
  );
}
