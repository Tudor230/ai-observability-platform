import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useExecution, useFailures, useSpans } from "../api/hooks";
import { PageHeader } from "../components/PageHeader";
import { RefreshButton } from "../components/RefreshButton";
import { TraceExplorer } from "../components/TraceExplorer";
import { KindBadge, KindIcon, StatusBadge } from "../components/domain";
import {
  Alert,
  Badge,
  Button,
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
import { toTraceSpans } from "../lib/traceSpans";
import { formatMoney, formatMs, formatTokens } from "../lib/format";
import type { FailureNode } from "../api/types";

type TabId = "spans" | "failures" | "metadata";

export default function ExecutionDetail() {
  const { id = "" } = useParams();
  const execution = useExecution(id);
  const spans = useSpans(id);
  const failures = useFailures(id);
  const [tab, setTab] = useState<TabId>("spans");

  const ex = execution.data;
  const spanItems = useMemo(() => spans.data?.items ?? [], [spans.data]);
  const traceSpans = useMemo(() => toTraceSpans(spanItems), [spanItems]);
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
            ) : traceSpans.length ? (
              <TraceExplorer key={ex.id} spans={traceSpans} />
            ) : (
              <EmptyState
                title="No spans"
                description="This execution has no normalized spans."
              />
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
