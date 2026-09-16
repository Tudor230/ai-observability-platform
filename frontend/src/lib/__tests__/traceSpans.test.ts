import { describe, expect, it } from "vitest";
import { toTraceRecord, toTraceSpans } from "../traceSpans";
import type { Execution, Span } from "../../api/types";

function span(partial: Partial<Span> & { span_id: string }): Span {
  const base: Span = {
    id: partial.span_id,
    span_id: partial.span_id,
    parent_id: null,
    kind: "CHAIN",
    name: null,
    status: "ok",
    error_type: null,
    error_message: null,
    error_kind: null,
    started_at: null,
    ended_at: null,
    duration_ms: null,
    llm_model: null,
    llm_provider: null,
    input_tokens: 0,
    output_tokens: 0,
    total_tokens: 0,
    tool_name: null,
    retrieval_doc_count: null,
    retry_count: 0,
    cost: null,
    attributes: null,
  };
  return { ...base, ...partial };
}

const execution: Partial<Execution> = {
  id: "ex-1",
  trace_id: "trace-1",
  workflow: "checkout",
  client_id: "client-42",
  duration_ms: 4200,
  total_cost: 0.0051,
  total_tokens: 2400,
  started_at: "2026-09-15T08:00:00Z",
};

describe("toTraceSpans", () => {
  it("nests children under their parents, ordered by start time", () => {
    const tree = toTraceSpans([
      span({
        span_id: "root",
        name: "workflow",
        started_at: "2026-09-15T08:00:00Z",
        duration_ms: 1000,
        ended_at: "2026-09-15T08:00:01Z",
      }),
      span({
        span_id: "late",
        parent_id: "root",
        name: "second",
        started_at: "2026-09-15T08:00:02Z",
      }),
      span({
        span_id: "early",
        parent_id: "root",
        name: "first",
        started_at: "2026-09-15T08:00:01Z",
      }),
    ]);

    expect(tree).toHaveLength(1);
    expect(tree[0].id).toBe("root");
    expect(tree[0].children?.map((child) => child.id)).toEqual(["early", "late"]);
  });

  it("treats orphaned spans as roots", () => {
    const tree = toTraceSpans([
      span({ span_id: "root" }),
      span({ span_id: "orphan", parent_id: "missing" }),
    ]);
    expect(tree.map((node) => node.id)).toEqual(["root", "orphan"]);
  });

  it("maps kinds, status, tokens and cost", () => {
    const [node] = toTraceSpans([
      span({
        span_id: "llm",
        kind: "LLM",
        status: "error",
        total_tokens: 1200,
        cost: 0.0031,
        error_message: "429 from provider",
        error_type: "RateLimitError",
        error_kind: "rate_limit",
        llm_model: "gpt-4o",
        llm_provider: "openai",
      }),
    ]);

    expect(node.type).toBe("llm_call");
    expect(node.status).toBe("error");
    expect(node.tokensCount).toBe(1200);
    expect(node.cost).toBe(0.0031);
    expect(node.metadata).toMatchObject({ model: "gpt-4o", provider: "openai" });
  });

  it("exposes the failure under the library's error attribute keys", () => {
    const [node] = toTraceSpans([
      span({ span_id: "tool", kind: "TOOL", status: "error", error_message: "boom" }),
    ]);
    expect(node.attributes).toEqual(
      expect.arrayContaining([
        { key: "error.message", value: { stringValue: "boom" } },
      ])
    );
    expect(JSON.parse(node.raw).statusMessage).toBe("boom");
  });
});

describe("toTraceRecord", () => {
  it("summarizes the execution and counts every span", () => {
    const spans = toTraceSpans([
      span({ span_id: "root" }),
      span({ span_id: "child", parent_id: "root" }),
      span({ span_id: "grandchild", parent_id: "child" }),
    ]);
    const record = toTraceRecord(execution as Execution, spans);

    expect(record.id).toBe("ex-1");
    expect(record.name).toBe("checkout");
    expect(record.spansCount).toBe(3);
    expect(record.agentDescription).toBe("client client-42");
    expect(record.durationMs).toBe(4200);
    expect(record.totalCost).toBe(0.0051);
  });
});
