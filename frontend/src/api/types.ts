export interface Overview {
  executions: number;
  failed_executions: number;
  error_rate: number;
  total_cost: number;
  total_tokens: number;
  llm_calls: number;
  tool_calls: number;
  avg_duration_ms: number;
  p50_duration_ms: number;
  p95_duration_ms: number;
  p99_duration_ms: number;
  deltas: {
    total_cost_pct: number | null;
    executions_pct: number | null;
    error_rate_pct: number | null;
  };
  open_alerts: number;
}

export interface Execution {
  id: string;
  trace_id: string;
  workflow_id: string | null;
  session_id: string | null;
  project_id: string | null;
  client_id: string | null;
  workflow: string | null;
  workflow_version: string | null;
  status: string;
  error_kind: string | null;
  error_message: string | null;
  metadata: Record<string, unknown> | null;
  started_at: string | null;
  ended_at: string | null;
  duration_ms: number | null;
  total_cost: number | null;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  llm_calls: number;
  tool_calls: number;
  retrieval_calls: number;
  agent_calls: number;
  error_count: number;
  retry_count: number;
  unpriced_calls: number;
  cost_complete: boolean;
}

export interface Span {
  id: string;
  span_id: string;
  parent_id: string | null;
  kind: string;
  name: string | null;
  status: string;
  error_type: string | null;
  error_message: string | null;
  error_kind: string | null;
  started_at: string | null;
  ended_at: string | null;
  duration_ms: number | null;
  llm_model: string | null;
  llm_provider: string | null;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  tool_name: string | null;
  retrieval_doc_count: number | null;
  retry_count: number;
  cost: number | null;
  attributes: Record<string, unknown> | null;
}

export interface FailureNode {
  span_id: string;
  parent_id: string | null;
  kind: string;
  name: string | null;
  status: string;
  error_kind: string | null;
  error_type: string | null;
  error_message: string | null;
  started_at: string | null;
}

export interface FailureTree {
  execution_id: string;
  error_count: number;
  nodes: FailureNode[];
}

export interface AggregateRow {
  key?: string;
  name?: string;
  client_id?: string;
  provider?: string;
  model?: string;
  executions: number;
  failed_executions?: number;
  error_rate?: number;
  total_cost: number | null;
  total_tokens: number;
  avg_duration_ms?: number;
  last_seen?: string | null;
  llm_calls?: number;
  input_tokens?: number;
  output_tokens?: number;
}

export interface DayMetric {
  day: string;
  dimension: string;
  dimension_key: string | null;
  executions: number;
  failed_executions: number;
  error_rate: number;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  llm_calls: number;
  tool_calls: number;
  total_cost: number;
  avg_duration_ms: number;
  p50_duration_ms: number;
  p95_duration_ms: number;
  p99_duration_ms: number;
}

export interface BudgetStatus {
  id: string;
  name: string | null;
  amount: number;
  spend: number;
  utilization: number;
  period: string;
  period_type: string;
  period_start: string;
  period_end: string;
  workflow_name: string | null;
}

export interface Alert {
  id: string;
  rule_id: string;
  severity: string;
  message: string;
  dimension: string;
  dimension_key: string | null;
  status: string;
  triggered_at: string | null;
}

export interface Filters {
  days: number;
  project_id?: string;
  client_id?: string;
  workflow?: string;
}
