"""Trace processing pipeline (plans/backend.md §6): normalize → enrich → classify
→ cost → persist executions/spans.

Phoenix-style ingest: spans are upserted by ``(execution, span_id)`` and a
trace's execution is recomputed from all stored spans. Batches may arrive in
any order or split mid-run (streaming SDK, HITL interrupt/resume) without
losing previously stored spans.
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
    """Explicit SDK workflow identity on a CHAIN span.

    ``session.id`` alone is not identity: the OpenInference LangChain
    instrumentor stamps it on LangGraph node spans (from the graph thread id),
    so a node arriving in a partial batch must never be mistaken for the
    workflow root. Phoenix treats sessions as attributes, not as roots.
    """
    a = d.raw.attributes
    return d.oi_kind == attrs.KIND_CHAIN and (
        attrs.SDK_WORKFLOW_ID in a or attrs.SDK_PROJECT_ID in a
    )


def _start_key(d: DerivedSpan) -> float:
    return d.raw.start_time.timestamp() if d.raw.start_time else 0.0


def _resolve_identity_root(
    session: Session, execution: Execution, derived: list[DerivedSpan]
) -> DerivedSpan | None:
    """Elect the span that defines this trace's workflow identity (F02).

    Phoenix-style root resolution: a span is a root when its parent is absent
    from **every span stored for the trace** (plus this batch), not merely from
    the current batch — a children-first delivery never invents a root from a
    node whose parent has not arrived yet. Explicit workflow roots win; a plain
    parentless span (``workflow()`` without ``workflow_id``) is the fallback.
    """
    stored_ids = set(
        session.execute(
            select(Span.span_id).where(Span.execution_id == execution.id)
        ).scalars()
    )
    present_ids = stored_ids | {d.raw.span_id for d in derived}
    parentless = [
        d
        for d in derived
        if d.raw.parent_span_id is None or d.raw.parent_span_id not in present_ids
    ]
    explicit = [d for d in parentless if _is_workflow_root(d)]
    if explicit:
        return min(explicit, key=_start_key)
    fallback = [d for d in parentless if not d.raw.parent_span_id]
    if fallback:
        return min(fallback, key=_start_key)
    return None


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
    """Persist one trace's batch, Phoenix-style: upsert spans, recompute.

    Spans are keyed by ``(execution, span_id)``: a re-sent span replaces its
    stored row and cost, new spans append, and no stored row is deleted because
    a later batch arrived. Aggregates, status and timing are always recomputed
    from *all* spans stored for the trace, so an interrupt run and its HITL
    resume (two roots, one trace id) coexist under a single execution.
    """
    trace_id = raw_spans[0].trace_id
    derived = [derive(r) for r in raw_spans]

    # Ingest validation: the authenticated project must match the identity of
    # every workflow root in the batch — a continued trace (LangGraph
    # interrupt/resume) carries two roots sharing one trace id. Nothing is
    # written before this check, so a rejected batch is a no-op.
    for d in derived:
        if not _is_workflow_root(d):
            continue
        asserted = attrs.as_str(d.raw.attributes, attrs.SDK_PROJECT_ID)
        if asserted and asserted != project.project_id:
            return {
                "trace_id": trace_id,
                "skipped": "project_mismatch",
                "detail": (
                    f"root sdk.project_id={asserted!r} != {project.project_id!r}"
                ),
            }

    existing = session.execute(
        select(Execution).where(Execution.trace_id == trace_id)
    ).scalar_one_or_none()
    if existing is not None and existing.project_id != project.id:
        # Trace-id collision across projects (deterministic workflow seeds):
        # keep the historical replace semantics instead of mixing projects.
        session.query(CostRecord).filter(
            CostRecord.execution_id == existing.id
        ).delete()
        session.query(Span).filter(Span.execution_id == existing.id).delete()
        session.delete(existing)
        session.flush()
        existing = None

    if existing is None:
        starts = [d.raw.start_time for d in derived if d.raw.start_time]
        execution = Execution(
            trace_id=trace_id,
            project_id=project.id,
            started_at=min(starts) if starts else _now(),
        )
        session.add(execution)
        session.flush()
    else:
        execution = existing

    # Store-aware root election: a children-first batch (streaming SDK) leaves
    # the execution provisional until its root arrives, then only the identity
    # is upgraded in place — stored spans are kept. The first resolved root
    # wins; a later HITL resume root must not flap the execution's identity.
    identity_root = _resolve_identity_root(session, execution, derived)

    # Server-authoritative identity (ADR-0008): explicit workflow roots always
    # carry the authenticated project, whatever the SDK sent (or omitted); the
    # elected fallback root does too.
    for d in derived:
        if _is_workflow_root(d) or (
            identity_root is not None
            and d.raw.span_id == identity_root.raw.span_id
        ):
            d.raw.attributes = {
                **d.raw.attributes,
                attrs.SDK_PROJECT_ID: project.project_id,
            }

    if identity_root is not None and execution.workflow_name is None:
        _apply_root_identity(session, execution, project, identity_root)

    summary = _upsert_spans(session, project, execution, derived)
    summary["provisional"] = execution.workflow_name is None
    return summary


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


def _upsert_spans(
    session: Session, project: Project, execution: Execution, derived: list[DerivedSpan]
) -> dict:
    """Upsert a batch of spans into an execution, then recompute aggregates.

    Spans are keyed by ``(execution, span_id)`` (Phoenix-style): a re-sent span
    replaces its stored row and cost, new spans append, everything else is
    kept. Aggregates always come from the full stored span set.
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
    """Rebuild execution aggregates from its stored spans (after an upsert)."""
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

    failed = [s for s in spans if s.status == "error" or s.error_kind]
    execution.error_count = len(failed)
    _attribute_failure(spans, failed, execution)
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


def _attribute_failure(
    spans: list[Span], failed: list[Span], execution: Execution
) -> None:
    """Attribute failures to their origin, Phoenix-style.

    Instrumentors mark **every ancestor** of a raising span as ERROR because
    the exception propagates through the run tree — that is faithful, and
    Phoenix renders it the same way. But only the span where the failure
    originated should carry a classification: a wrapper CHAIN/AGENT whose
    failure is just a re-raised descendant drops the generic
    ``business_logic`` fallback. The execution then reports the earliest
    classified failure (the originating span) as its root cause.
    """
    if not failed:
        execution.status = "ok"
        execution.root_error_kind = None
        execution.root_error_message = None
        return

    execution.status = "error"
    children: dict[str | None, list[Span]] = {}
    for span in spans:
        children.setdefault(span.parent_id, []).append(span)
    specific = {
        s.span_id
        for s in failed
        if s.error_kind and s.error_kind != c.KIND_BUSINESS_LOGIC
    }

    def has_specific_descendant(span_id: str) -> bool:
        stack = list(children.get(span_id, ()))
        seen: set[str] = set()
        while stack:
            child = stack.pop()
            if child.span_id in seen:
                continue
            seen.add(child.span_id)
            if child.span_id in specific:
                return True
            stack.extend(children.get(child.span_id, ()))
        return False

    for span in failed:
        if (
            span.error_kind == c.KIND_BUSINESS_LOGIC
            and span.kind in (attrs.KIND_CHAIN, attrs.KIND_AGENT)
            and has_specific_descendant(span.span_id)
        ):
            # The wrapper only propagated a classified descendant's failure.
            span.error_kind = None

    primary = min(
        (s for s in failed if s.error_kind) or failed,
        key=lambda s: s.started_at.timestamp() if s.started_at else 0,
    )
    execution.root_error_kind = primary.error_kind
    execution.root_error_message = primary.error_message


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