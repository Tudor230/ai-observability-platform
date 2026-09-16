"""Trace processing pipeline (plans/backend.md §6): normalize → enrich → classify
→ cost → persist executions/spans.

Idempotent per trace_id: re-processing a trace fully recomputes its rows.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import aiobs_contracts as c
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import attrs
from ..classify import classify_span, is_failed
from ..cost import PricingResolver, compute_llm_cost
from ..models import (
    Agent,
    Client,
    CostRecord,
    Execution,
    Pricing,
    Project,
    Span,
    Workflow,
)
from .otlp import RawSpan

logger = logging.getLogger(__name__)


def _duration_ms(start: datetime | None, end: datetime | None) -> float | None:
    if start and end:
        return max(0.0, (end - start).total_seconds() * 1000.0)
    return None


def _price_snapshot(pricing: Pricing) -> dict:
    """Rates resolved for a cost record, kept so history survives price edits (F30)."""
    return {
        "currency": pricing.currency,
        "input": float(pricing.input_price_per_1m or 0.0),
        "output": float(pricing.output_price_per_1m or 0.0),
        "cache_read": (
            float(pricing.cache_read_price_per_1m)
            if pricing.cache_read_price_per_1m is not None
            else None
        ),
        "cache_write": (
            float(pricing.cache_write_price_per_1m)
            if pricing.cache_write_price_per_1m is not None
            else None
        ),
        "reasoning": (
            float(pricing.reasoning_price_per_1m)
            if pricing.reasoning_price_per_1m is not None
            else None
        ),
        "effective_from": (
            pricing.effective_from.isoformat() if pricing.effective_from else None
        ),
    }


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


def _is_workflow_root(d: DerivedSpan) -> bool:
    a = d.raw.attributes
    return d.oi_kind == attrs.KIND_CHAIN and (
        attrs.SDK_WORKFLOW_ID in a or attrs.SDK_PROJECT_ID in a or "session.id" in a
    )


def _start_key(d: DerivedSpan) -> float:
    return d.raw.start_time.timestamp() if d.raw.start_time else 0.0


def _find_root(derived: list[DerivedSpan]) -> DerivedSpan | None:
    """Return the trace root only when this batch can prove one (F02).

    A batch may be a *partial* re-send: children whose parent lives in a
    previous batch. Treating such children as roots would create a bogus
    execution, so a root must be either
    1. the SDK workflow root (CHAIN carrying ``sdk.*`` identity), or
    2. a span with no recorded parent at all.
    Batches that only contain parented spans that are not in the batch return
    ``None`` and are merged into an existing execution (or skipped).
    """
    span_ids = {d.raw.span_id for d in derived}
    is_parentless = lambda d: d.raw.parent_span_id not in span_ids  # noqa: E731
    candidates = [d for d in derived if _is_workflow_root(d) and is_parentless(d)]
    if not candidates:
        candidates = [
            d for d in derived if is_parentless(d) and not d.raw.parent_span_id
        ]
    if not candidates:
        return None
    return min(candidates, key=_start_key)


def _primary_failure(
    root: DerivedSpan, failed: list[DerivedSpan]
) -> DerivedSpan | None:
    """Pick the most specific failure (F28).

    A wrapper root often carries only a generic propagated kind; prefer the
    earliest failing descendant when it has a more specific classification.
    """
    if not failed:
        return None
    descendants = [d for d in failed if d.raw.span_id != root.raw.span_id]
    if descendants:
        earliest = min(descendants, key=_start_key)
        if earliest.error_kind or not root.error_kind:
            return earliest
    return root if root.failed else min(failed, key=_start_key)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def process_trace_batch(
    session: Session, project: Project, raw_spans: list[RawSpan]
) -> list[dict]:
    """Persist all traces in one OTLP batch. Returns per-trace summaries.

    Each trace runs in its own savepoint so one bad trace cannot roll back the
    whole request (F21); failures are reported per trace.
    """
    grouped: dict[str, list[RawSpan]] = {}
    for raw in raw_spans:
        grouped.setdefault(raw.trace_id, []).append(raw)
    results = []
    for trace_id, spans in grouped.items():
        try:
            with session.begin_nested():
                results.append(process_trace(session, project, spans))
        except Exception as exc:  # noqa: BLE001 - report, keep the rest of the batch
            logger.exception("trace %s failed to process", trace_id)
            results.append(
                {
                    "trace_id": trace_id,
                    "skipped": "processing_error",
                    "detail": str(exc),
                }
            )
    return results


def process_trace(
    session: Session, project: Project, raw_spans: list[RawSpan]
) -> dict:
    trace_id = raw_spans[0].trace_id
    derived = [derive(r) for r in raw_spans]
    root = _find_root(derived)

    existing = session.execute(
        select(Execution).where(Execution.trace_id == trace_id)
    ).scalar_one_or_none()

    if root is None:
        # Partial batch (children whose parent is not here). Never invent a root
        # and never delete stored rows; merge into an existing execution if one
        # exists (F02). A streaming SDK can deliver children before the root, so
        # otherwise keep them in a *provisional* execution instead of dropping
        # them; the root batch later rebuilds the execution with full identity.
        if existing is not None:
            return _merge_partial_batch(session, existing, derived, project)
        return _provisional_batch(session, project, derived, trace_id)

    root_a = root.raw.attributes
    # Ingest validation: the authenticated project must match the root's identity.
    # Rows are only deleted *after* this check, so a rejected batch is a no-op.
    root_project = attrs.as_str(root_a, attrs.SDK_PROJECT_ID)
    if root_project and root_project != project.project_id:
        return {
            "trace_id": trace_id,
            "skipped": "project_mismatch",
            "detail": f"root sdk.project_id={root_project!r} != {project.project_id!r}",
        }

    # Validated root in hand: idempotent recompute may safely replace old rows,
    # unless the stored execution is *provisional* (children arrived first) —
    # then keep the stored spans and upgrade the identity in place.
    if existing:
        if existing.workflow_name is None:
            _apply_root_identity(session, existing, project, root)
            return _merge_partial_batch(session, existing, derived, project)
        session.query(CostRecord).filter(
            CostRecord.execution_id == existing.id
        ).delete()
        session.query(Span).filter(Span.execution_id == existing.id).delete()
        session.delete(existing)
        session.flush()

    started = root.raw.start_time or min(
        (d.raw.start_time for d in derived if d.raw.start_time), default=None
    )
    ended = root.raw.end_time or max(
        (d.raw.end_time for d in derived if d.raw.end_time), default=None
    )
    started = started or _now()

    execution = Execution(
        trace_id=trace_id,
        project_id=project.id,
        started_at=started,
        ended_at=ended,
        duration_ms=_duration_ms(started, ended),
    )
    session.add(execution)
    session.flush()
    _apply_root_identity(session, execution, project, root)

    resolver = PricingResolver(session, started)
    failed: list[DerivedSpan] = []
    span_rows: list[Span] = []
    cost_rows: list[CostRecord] = []
    total_cost = Decimal("0")
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

        span_cost: Decimal | None = None
        if kind == attrs.KIND_LLM:
            pricing = resolver.resolve(d.provider, d.model)
            if pricing is not None:
                amount = compute_llm_cost(
                    pricing,
                    d.input_tokens,
                    d.output_tokens,
                    cache_read_tokens=d.cache_read_tokens,
                    cache_write_tokens=d.cache_write_tokens,
                    reasoning_tokens=d.reasoning_tokens,
                )
                if amount is not None:
                    span_cost = Decimal(str(amount))
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
                            unit_prices=_price_snapshot(pricing),
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
            attributes=root_a if is_root else d.raw.attributes,
        )
        span_rows.append(row)

    session.add_all(span_rows)
    session.add_all(cost_rows)

    # Root propagation (consistent with SDK enrichment). Prefer the most
    # specific failing descendant over a generic root wrapper (F28).
    if root.failed or failed:
        execution.status = "error"
        primary = _primary_failure(root, failed) or root
        execution.root_error_kind = primary.error_kind
        execution.root_error_message = primary.error_message
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
    execution.total_cost = (
        total_cost.quantize(Decimal("0.000001")) if priced_calls else None
    )
    # Unpriced LLM calls: cost must stay auditable, never silently $0 (F12).
    execution.unpriced_calls = llm_calls - priced_calls
    execution.duration_ms = execution.duration_ms or _duration_ms(started, ended)
    touch_agents(session, project, derived)
    session.flush()

    return {
        "trace_id": trace_id,
        "execution_id": execution.id,
        "status": execution.status,
        "error_kind": execution.root_error_kind,
        "spans": len(span_rows),
        "unpriced_calls": execution.unpriced_calls,
        "total_cost": float(total_cost),
        "total_tokens": total_tokens,
    }


def _apply_root_identity(
    session: Session, execution: Execution, project: Project, root: DerivedSpan
) -> None:
    """Copy workflow identity/metadata from a validated root onto an execution."""
    root_a = root.raw.attributes
    client_key = attrs.as_str(root_a, attrs.SDK_CLIENT_ID)
    client = _upsert_client(session, client_key) if client_key else None
    wf_name = root.raw.name or root.oi_kind
    wf_version = attrs.as_str(root_a, attrs.SDK_WORKFLOW_VERSION)
    workflow = _upsert_workflow(session, project, wf_name, wf_version)
    execution.workflow_id = attrs.as_str(root_a, attrs.SDK_WORKFLOW_ID)
    execution.session_id = attrs.as_str(root_a, attrs.SESSION_ID)
    execution.client_id = client.id if client else None
    execution.workflow_name = wf_name
    execution.workflow_ref = workflow.id
    execution.workflow_version = wf_version
    execution.metadata_json = c.redact_metadata(attrs.metadata_dict(root.raw))


def _provisional_batch(
    session: Session, project: Project, derived: list[DerivedSpan], trace_id: str
) -> dict:
    """Store a children-first batch before its root arrives (F02/F14).

    The execution has no workflow identity yet; the root batch later rebuilds
    it (same trace_id) with the real identity and the complete span set.
    """
    starts = [d.raw.start_time for d in derived if d.raw.start_time]
    execution = Execution(
        trace_id=trace_id,
        project_id=project.id,
        started_at=min(starts) if starts else _now(),
        ended_at=max(starts) if starts else None,
    )
    session.add(execution)
    session.flush()
    summary = _merge_partial_batch(session, execution, derived, project)
    summary["provisional"] = True
    return summary


def _merge_partial_batch(
    session: Session, execution: Execution, derived: list[DerivedSpan], project: Project
) -> dict:
    """Upsert a children-only batch into an existing execution (F02).

    Spans already stored are replaced, the rest are kept; aggregates are then
    recomputed from the stored spans. The execution itself is never deleted.
    """
    resolver = PricingResolver(session, execution.started_at)
    batch_ids = [d.raw.span_id for d in derived]
    session.query(CostRecord).filter(
        CostRecord.execution_id == execution.id, CostRecord.span_id.in_(batch_ids)
    ).delete(synchronize_session=False)
    session.query(Span).filter(
        Span.execution_id == execution.id, Span.span_id.in_(batch_ids)
    ).delete(synchronize_session=False)
    session.flush()

    for d in derived:
        span_cost: Decimal | None = None
        if d.oi_kind == attrs.KIND_LLM:
            pricing = resolver.resolve(d.provider, d.model)
            if pricing is not None:
                amount = compute_llm_cost(
                    pricing,
                    d.input_tokens,
                    d.output_tokens,
                    cache_read_tokens=d.cache_read_tokens,
                    cache_write_tokens=d.cache_write_tokens,
                    reasoning_tokens=d.reasoning_tokens,
                )
                if amount is not None:
                    span_cost = Decimal(str(amount))
                    session.add(
                        CostRecord(
                            execution_id=execution.id,
                            span_id=d.raw.span_id,
                            provider=d.provider,
                            model=d.model,
                            input_tokens=d.input_tokens,
                            output_tokens=d.output_tokens,
                            price_version=pricing.id,
                            unit_prices=_price_snapshot(pricing),
                            amount=span_cost,
                        )
                    )
        session.add(
            Span(
                execution_id=execution.id,
                trace_id=execution.trace_id,
                span_id=d.raw.span_id,
                parent_id=d.raw.parent_span_id,
                kind=d.oi_kind,
                name=d.raw.name or None,
                status=d.raw.status_code,
                error_type=d.error_type,
                error_message=d.error_message,
                error_kind=d.error_kind,
                started_at=d.raw.start_time or execution.started_at,
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
                attributes=d.raw.attributes,
            )
        )
    session.flush()
    touch_agents(session, project, derived)
    return _recompute_execution(session, execution, merged=len(derived))


def _recompute_execution(
    session: Session, execution: Execution, merged: int = 0
) -> dict:
    """Rebuild execution aggregates from its stored spans (after a merge)."""
    spans = (
        session.execute(
            select(Span)
            .where(Span.execution_id == execution.id)
            .order_by(Span.started_at)
        )
        .scalars()
        .all()
    )
    execution.input_tokens = sum(s.input_tokens for s in spans)
    execution.output_tokens = sum(s.output_tokens for s in spans)
    execution.total_tokens = sum(s.total_tokens for s in spans)
    execution.llm_calls = sum(1 for s in spans if s.kind == attrs.KIND_LLM)
    execution.tool_calls = sum(1 for s in spans if s.kind == attrs.KIND_TOOL)
    execution.retrieval_calls = sum(1 for s in spans if s.kind == attrs.KIND_RETRIEVER)
    execution.agent_calls = sum(1 for s in spans if s.kind == attrs.KIND_AGENT)
    execution.retry_count = max((s.retry_count for s in spans), default=0)
    failed = [s for s in spans if s.status == "error" or s.error_kind]
    execution.error_count = len(failed)
    costs = [s.cost for s in spans if s.cost is not None]
    execution.total_cost = (
        sum(costs, Decimal("0")).quantize(Decimal("0.000001")) if costs else None
    )
    execution.unpriced_calls = execution.llm_calls - len(costs)

    starts = [s.started_at for s in spans if s.started_at]
    ends = [s.ended_at for s in spans if s.ended_at]
    if starts:
        execution.started_at = min(starts)
    if ends:
        execution.ended_at = max(ends)
        execution.duration_ms = _duration_ms(execution.started_at, execution.ended_at)

    if failed:
        execution.status = "error"
        root_span = next((s for s in spans if not s.parent_id), None)
        descendants = [
            s for s in failed if root_span is None or s.span_id != root_span.span_id
        ]
        if descendants:
            primary = min(
                descendants,
                key=lambda s: s.started_at.timestamp() if s.started_at else 0,
            )
            if not primary.error_kind and root_span is not None and root_span.error_kind:
                primary = root_span
        else:
            primary = failed[0]
        execution.root_error_kind = primary.error_kind
        execution.root_error_message = primary.error_message
    else:
        execution.status = "ok"
        execution.root_error_kind = None
        execution.root_error_message = None
    session.flush()

    return {
        "trace_id": execution.trace_id,
        "execution_id": execution.id,
        "status": execution.status,
        "error_kind": execution.root_error_kind,
        "spans": len(spans),
        "merged": merged,
        "unpriced_calls": execution.unpriced_calls,
        "total_cost": float(execution.total_cost or 0),
        "total_tokens": execution.total_tokens,
    }


def _upsert_row(session: Session, model, lookup, values: dict):
    """Insert-or-select with retry, safe under concurrent exporters (F27).

    Two exporters sending the same client/workflow/agent concurrently would
    otherwise race between the SELECT and the INSERT; the losing insert is
    retried as a lookup once the winning transaction commits.
    """
    row = session.execute(select(model).where(lookup)).scalar_one_or_none()
    if row is not None:
        return row, False
    try:
        with session.begin_nested():
            row = model(**values)
            session.add(row)
            session.flush()
        return row, True
    except IntegrityError:
        row = session.execute(select(model).where(lookup)).scalar_one()
        return row, False


def _upsert_client(session: Session, client_key: str) -> Client:
    row, created = _upsert_row(
        session,
        Client,
        Client.external_key == client_key,
        {"external_key": client_key, "name": client_key},
    )
    if not created:
        row.last_seen = _now()
    return row


def _upsert_workflow(
    session: Session, project: Project, name: str, version: str | None
) -> Workflow:
    row, created = _upsert_row(
        session,
        Workflow,
        (Workflow.project_id == project.id)
        & (Workflow.name == name)
        & (Workflow.version == version),
        {"project_id": project.id, "name": name, "version": version},
    )
    if not created:
        row.last_seen = _now()
    return row


def touch_agents(session: Session, project: Project, derived: list[DerivedSpan]) -> None:
    """Ensure AGENT dimension rows exist for seen agent names (per project, F25)."""
    names = {
        d.raw.name
        for d in derived
        if d.oi_kind == attrs.KIND_AGENT and d.raw.name
    }
    for name in names:
        row, created = _upsert_row(
            session,
            Agent,
            (Agent.project_id == project.id) & (Agent.name == name),
            {"project_id": project.id, "name": name},
        )
        if not created:
            row.last_seen = _now()
    session.flush()