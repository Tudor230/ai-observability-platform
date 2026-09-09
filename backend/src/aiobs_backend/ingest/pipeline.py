"""Trace processing pipeline (plans/backend.md §6): normalize → enrich → classify
→ cost → persist executions/spans.

Idempotent per trace_id: re-processing a trace fully recomputes its rows.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import aiobs_contracts as c
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import attrs
from ..classify import classify_span, is_failed
from ..cost import PricingResolver, compute_llm_cost
from ..models import (
    Agent,
    Client,
    CostRecord,
    Execution,
    Project,
    Span,
    Workflow,
)
from .otlp import RawSpan


def trim_attributes(attributes: dict[str, object]) -> dict[str, object]:
    """Drop captured payloads from the stored attribute snapshot (privacy + size)."""
    return {k: v for k, v in attributes.items() if not c.is_payload_attribute(k)}


def _duration_ms(start: datetime | None, end: datetime | None) -> float | None:
    if start and end:
        return max(0.0, (end - start).total_seconds() * 1000.0)
    return None


@dataclass
class DerivedSpan:
    raw: RawSpan
    oi_kind: str = attrs.KIND_UNKNOWN
    failed: bool = False
    error_kind: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    model: str | None = None
    provider: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    tool_name: str | None = None
    retrieval_docs: int | None = None
    retry: int = 0
    duration_ms: float | None = None
    cost: float | None = None


def derive(raw: RawSpan) -> DerivedSpan:
    a = raw.attributes
    d = DerivedSpan(raw=raw, oi_kind=attrs.span_kind(raw))
    d.failed = is_failed(raw)
    if d.failed:
        d.error_kind, d.error_type, d.error_message = classify_span(raw)
    d.model = attrs.as_str(a, attrs.LLM_MODEL)
    d.provider = attrs.as_str(a, attrs.LLM_PROVIDER)
    d.input_tokens = attrs.as_int(a, attrs.LLM_PROMPT_TOKENS)
    d.output_tokens = attrs.as_int(a, attrs.LLM_COMPLETION_TOKENS)
    d.total_tokens = attrs.as_int(a, attrs.LLM_TOTAL_TOKENS)
    if not d.total_tokens:
        d.total_tokens = d.input_tokens + d.output_tokens
    d.cache_read_tokens = attrs.as_int(a, attrs.LLM_CACHE_READ_TOKENS)
    d.cache_write_tokens = attrs.as_int(a, attrs.LLM_CACHE_WRITE_TOKENS)
    d.reasoning_tokens = attrs.as_int(a, attrs.LLM_REASONING_TOKENS)
    d.tool_name = attrs.as_str(a, attrs.TOOL_NAME)
    d.retrieval_docs = attrs.retrieval_doc_count(raw)
    d.retry = attrs.retry_count(a)
    d.duration_ms = _duration_ms(raw.start_time, raw.end_time)
    return d


def _find_root(derived: list[DerivedSpan]) -> DerivedSpan | None:
    span_ids = {d.raw.span_id for d in derived}
    parentless = [d for d in derived if d.raw.parent_span_id not in span_ids]
    if not parentless:
        return None
    # Prefer the SDK workflow root (CHAIN with business identity), else earliest.
    def _score(d: DerivedSpan) -> tuple[int, int]:
        a = d.raw.attributes
        is_wf = d.oi_kind == attrs.KIND_CHAIN and (
            attrs.SDK_WORKFLOW_ID in a or attrs.SDK_PROJECT_ID in a or "session.id" in a
        )
        start = d.raw.start_time
        order = start.timestamp() if start else 0
        return (0 if is_wf else 1, order)

    return min(parentless, key=_score)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def process_trace_batch(
    session: Session, project: Project, raw_spans: list[RawSpan]
) -> list[dict]:
    """Persist all traces in one OTLP batch. Returns per-trace summaries."""
    grouped: dict[str, list[RawSpan]] = {}
    for raw in raw_spans:
        grouped.setdefault(raw.trace_id, []).append(raw)
    results = []
    for trace_id, spans in grouped.items():
        results.append(process_trace(session, project, spans))
    return results


def process_trace(
    session: Session, project: Project, raw_spans: list[RawSpan]
) -> dict:
    trace_id = raw_spans[0].trace_id
    # Idempotent recompute: clear any previous rows for this trace.
    existing = session.execute(
        select(Execution).where(Execution.trace_id == trace_id)
    ).scalar_one_or_none()
    if existing:
        session.query(CostRecord).filter(
            CostRecord.execution_id == existing.id
        ).delete()
        session.query(Span).filter(Span.execution_id == existing.id).delete()
        session.delete(existing)
        session.flush()

    derived = [derive(r) for r in raw_spans]
    root = _find_root(derived)
    if root is None:
        return {"trace_id": trace_id, "skipped": "no root span"}

    root_a = root.raw.attributes
    client_key = attrs.as_str(root_a, attrs.SDK_CLIENT_ID)
    client = _upsert_client(session, client_key) if client_key else None
    wf_name = root.raw.name or root.oi_kind
    wf_version = attrs.as_str(root_a, attrs.SDK_WORKFLOW_VERSION)
    workflow = _upsert_workflow(session, project, wf_name, wf_version)

    started = root.raw.start_time or min(
        (d.raw.start_time for d in derived if d.raw.start_time), default=None
    )
    ended = root.raw.end_time or max(
        (d.raw.end_time for d in derived if d.raw.end_time), default=None
    )
    started = started or _now()

    execution = Execution(
        trace_id=trace_id,
        workflow_id=attrs.as_str(root_a, attrs.SDK_WORKFLOW_ID),
        session_id=attrs.as_str(root_a, attrs.SESSION_ID),
        project_id=project.id,
        client_id=client.id if client else None,
        workflow_name=wf_name,
        workflow_ref=workflow.id,
        workflow_version=wf_version,
        metadata_json=attrs.metadata_dict(root.raw),
        started_at=started,
        ended_at=ended,
        duration_ms=_duration_ms(started, ended),
    )
    session.add(execution)
    session.flush()

    resolver = PricingResolver(session, started)
    failed: list[DerivedSpan] = []
    span_rows: list[Span] = []
    cost_rows: list[CostRecord] = []
    total_cost = 0.0
    priced_calls = 0
    llm_calls = tool_calls = retrieval_calls = agent_calls = error_count = retries = 0
    input_tokens = output_tokens = total_tokens = 0

    for d in derived:
        is_root = d.raw.span_id == root.raw.span_id
        kind = d.oi_kind
        if kind == attrs.KIND_LLM:
            llm_calls += 1
            input_tokens += d.input_tokens
            output_tokens += d.output_tokens
            total_tokens += d.total_tokens
        elif kind == attrs.KIND_TOOL:
            tool_calls += 1
        elif kind == attrs.KIND_RETRIEVER:
            retrieval_calls += 1
        elif kind == attrs.KIND_AGENT:
            agent_calls += 1

        if d.retry:
            retries = max(retries, d.retry)
        if d.failed:
            error_count += 1
            failed.append(d)

        span_cost: float | None = None
        if kind == attrs.KIND_LLM:
            pricing = resolver.resolve(d.provider, d.model)
            if pricing is not None:
                span_cost = compute_llm_cost(
                    pricing,
                    d.input_tokens,
                    d.output_tokens,
                    cache_read_tokens=d.cache_read_tokens,
                    cache_write_tokens=d.cache_write_tokens,
                    reasoning_tokens=d.reasoning_tokens,
                )
                total_cost += span_cost
                priced_calls += 1
                cost_rows.append(
                    CostRecord(
                        execution_id=execution.id,
                        span_id=d.raw.span_id,
                        provider=d.provider,
                        model=d.model,
                        input_tokens=d.input_tokens,
                        output_tokens=d.output_tokens,
                        price_version=pricing.id,
                        amount=span_cost,
                    )
                )

        row = Span(
            execution_id=execution.id,
            trace_id=trace_id,
            span_id=d.raw.span_id,
            parent_id=d.raw.parent_span_id,
            kind=kind,
            name=d.raw.name or None,
            status=d.raw.status_code,
            error_type=d.error_type,
            error_message=d.error_message,
            error_kind=d.error_kind,
            started_at=d.raw.start_time or started,
            ended_at=d.raw.end_time,
            duration_ms=d.duration_ms,
            llm_model=d.model,
            llm_provider=d.provider,
            input_tokens=d.input_tokens,
            output_tokens=d.output_tokens,
            total_tokens=d.total_tokens,
            tool_name=d.tool_name,
            retrieval_doc_count=d.retrieval_docs,
            retry_count=d.retry,
            cost=span_cost,
            attributes=trim_attributes(root_a if is_root else d.raw.attributes),
        )
        span_rows.append(row)

    session.add_all(span_rows)
    session.add_all(cost_rows)

    # Root propagation (consistent with SDK enrichment).
    if root.failed or failed:
        execution.status = "error"
        primary = root if root.failed else min(failed, key=lambda x: x.raw.start_time.timestamp() if x.raw.start_time else 0)
        execution.root_error_kind = primary.error_kind or (failed[0].error_kind if failed else None)
        execution.root_error_message = primary.error_message or (failed[0].error_message if failed else None)
    else:
        execution.status = "ok"

    execution.input_tokens = input_tokens
    execution.output_tokens = output_tokens
    execution.total_tokens = total_tokens
    execution.llm_calls = llm_calls
    execution.tool_calls = tool_calls
    execution.retrieval_calls = retrieval_calls
    execution.agent_calls = agent_calls
    execution.error_count = error_count
    execution.retry_count = retries
    execution.total_cost = round(total_cost, 6) if priced_calls else None
    execution.duration_ms = execution.duration_ms or _duration_ms(started, ended)
    touch_agents(session, derived)
    session.flush()

    return {
        "trace_id": trace_id,
        "execution_id": execution.id,
        "status": execution.status,
        "error_kind": execution.root_error_kind,
        "spans": len(span_rows),
        "total_cost": total_cost,
        "total_tokens": total_tokens,
    }


def _upsert_client(session: Session, client_key: str) -> Client:
    row = session.execute(
        select(Client).where(Client.external_key == client_key)
    ).scalar_one_or_none()
    if row:
        row.last_seen = _now()
        return row
    row = Client(external_key=client_key, name=client_key)
    session.add(row)
    session.flush()
    return row


def _upsert_workflow(
    session: Session, project: Project, name: str, version: str | None
) -> Workflow:
    row = session.execute(
        select(Workflow).where(
            Workflow.project_id == project.id,
            Workflow.name == name,
            Workflow.version == version,
        )
    ).scalar_one_or_none()
    if row:
        row.last_seen = _now()
        return row
    row = Workflow(
        project_id=project.id, name=name, version=version
    )
    session.add(row)
    session.flush()
    return row


def touch_agents(session: Session, derived: list[DerivedSpan]) -> None:
    """Ensure AGENT dimension rows exist for seen agent names."""
    names = {
        d.raw.name
        for d in derived
        if d.oi_kind == attrs.KIND_AGENT and d.raw.name
    }
    for name in names:
        row = session.execute(
            select(Agent).where(Agent.name == name)
        ).scalar_one_or_none()
        if row:
            row.last_seen = _now()
        else:
            session.add(Agent(name=name))
    session.flush()