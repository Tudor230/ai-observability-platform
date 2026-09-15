import type {
  TraceRecord,
  TraceSpan,
  TraceSpanAttribute,
  TraceSpanAttributeValue,
  TraceSpanCategory,
} from "@evilmartians/agent-prism-types";
import type { Execution, Span } from "../api/types";

/**
 * Adapts the backend's normalized spans/executions onto the AgentPrism
 * normalized types (`TraceSpan` / `TraceRecord`) so the vendored viewer can
 * render them without any further glue.
 */

const KIND_TO_CATEGORY: Record<string, TraceSpanCategory> = {
  LLM: "llm_call",
  TOOL: "tool_execution",
  AGENT: "agent_invocation",
  CHAIN: "chain_operation",
  RETRIEVER: "retrieval",
  EMBEDDING: "embedding",
  GUARDRAIL: "guardrail",
  EVENT: "event",
};

/** Attribute keys AgentPrism's error surface reads (see its data package). */
const ERROR_MESSAGE_KEYS = ["error.message", "status.message", "exception.message"];
const ERROR_STACK_KEYS = ["error.stack", "exception.stacktrace", "exception.stack"];

const INPUT_KEYS = ["input.value", "input", "llm.input_messages", "gen_ai.prompt"];
const OUTPUT_KEYS = ["output.value", "output", "llm.output_messages", "gen_ai.completion"];

function toAttributeValue(value: unknown): TraceSpanAttributeValue {
  if (typeof value === "string") return { stringValue: value };
  if (typeof value === "boolean") return { boolValue: value };
  if (typeof value === "number" && Number.isFinite(value)) {
    return { intValue: String(value) };
  }
  if (value === null || value === undefined) return { stringValue: "" };
  return { stringValue: JSON.stringify(value) };
}

function toAttributes(span: Span): TraceSpanAttribute[] {
  const attributes: TraceSpanAttribute[] = Object.entries(span.attributes ?? {}).map(
    ([key, value]) => ({ key, value: toAttributeValue(value) })
  );

  // The library extracts error surfaces from well-known attribute keys; expose
  // the backend's classified failure under those keys.
  const known = new Set(attributes.map((attribute) => attribute.key));
  if (span.error_message && !ERROR_MESSAGE_KEYS.some((key) => known.has(key))) {
    attributes.push({ key: "error.message", value: { stringValue: span.error_message } });
  }
  if (span.error_type && !known.has("error.type")) {
    attributes.push({ key: "error.type", value: { stringValue: span.error_type } });
  }
  const stack = readString(span.attributes, ERROR_STACK_KEYS);
  if (stack && !ERROR_STACK_KEYS.some((key) => known.has(key))) {
    attributes.push({ key: "error.stack", value: { stringValue: stack } });
  }
  return attributes;
}

function readString(
  attributes: Record<string, unknown> | null | undefined,
  keys: readonly string[]
): string | undefined {
  if (!attributes) return undefined;
  for (const key of keys) {
    const value = attributes[key];
    if (typeof value === "string" && value.trim()) return value;
    if (value !== undefined && value !== null && typeof value !== "string") {
      return JSON.stringify(value, null, 2);
    }
  }
  return undefined;
}

function statusOf(span: Span): TraceSpan["status"] {
  if (span.status === "error") return "error";
  if (span.status === "ok" || span.status === "success") return "success";
  if (span.status === "warning") return "warning";
  return "pending";
}

function toTraceSpan(span: Span): TraceSpan {
  const start = span.started_at ? new Date(span.started_at) : new Date(0);
  const end = span.ended_at
    ? new Date(span.ended_at)
    : new Date(start.getTime() + (span.duration_ms ?? 0));

  return {
    id: span.span_id,
    title: span.name ?? span.span_id,
    startTime: start,
    endTime: end,
    duration: span.duration_ms ?? 0,
    type: KIND_TO_CATEGORY[span.kind] ?? "span",
    status: statusOf(span),
    raw: JSON.stringify(
      {
        name: span.name,
        kind: span.kind,
        status: span.status,
        statusMessage: span.error_message ?? undefined,
        attributes: span.attributes ?? {},
      },
      null,
      2
    ),
    attributes: toAttributes(span),
    input: readString(span.attributes, INPUT_KEYS),
    output: readString(span.attributes, OUTPUT_KEYS),
    tokensCount: span.total_tokens > 0 ? span.total_tokens : undefined,
    cost: span.cost ?? undefined,
    metadata: {
      kind: span.kind,
      model: span.llm_model ?? undefined,
      provider: span.llm_provider ?? undefined,
      toolName: span.tool_name ?? undefined,
      retrievalDocumentCount: span.retrieval_doc_count ?? undefined,
      retryCount: span.retry_count,
      errorKind: span.error_kind ?? undefined,
      errorType: span.error_type ?? undefined,
      errorMessage: span.error_message ?? undefined,
    },
  };
}

/**
 * Converts the flat span list into the AgentPrism span forest (root spans with
 * `children`), ordered by start time like the trace itself.
 */
export function toTraceSpans(spans: Span[]): TraceSpan[] {
  const ids = new Set(spans.map((span) => span.span_id));
  const byParent = new Map<string | null, Span[]>();

  for (const span of spans) {
    const parent = span.parent_id && ids.has(span.parent_id) ? span.parent_id : null;
    const siblings = byParent.get(parent) ?? [];
    siblings.push(span);
    byParent.set(parent, siblings);
  }

  for (const siblings of byParent.values()) {
    siblings.sort((a, b) => {
      const aStart = a.started_at ? Date.parse(a.started_at) : 0;
      const bStart = b.started_at ? Date.parse(b.started_at) : 0;
      return aStart - bStart;
    });
  }

  const build = (parentId: string | null): TraceSpan[] =>
    (byParent.get(parentId) ?? []).map((span) => {
      const node = toTraceSpan(span);
      const children = build(span.span_id);
      return children.length ? { ...node, children } : node;
    });

  return build(null);
}

/** Builds the AgentPrism trace record for the execution header. */
export function toTraceRecord(execution: Execution, spans: TraceSpan[]): TraceRecord {
  const count = countSpans(spans);
  return {
    id: execution.id,
    name: execution.workflow ?? execution.trace_id,
    spansCount: count,
    durationMs: execution.duration_ms ?? 0,
    agentDescription: execution.client_id
      ? `client ${execution.client_id}`
      : execution.project_id
        ? `project ${execution.project_id}`
        : execution.trace_id,
    totalCost: execution.total_cost ?? undefined,
    totalTokens: execution.total_tokens,
    startTime: execution.started_at ? Date.parse(execution.started_at) : undefined,
  };
}

function countSpans(spans: TraceSpan[]): number {
  return spans.reduce((total, span) => total + 1 + countSpans(span.children ?? []), 0);
}
