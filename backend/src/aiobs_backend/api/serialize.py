"""Serialization helpers (ORM → plain dicts) for the read API."""
from __future__ import annotations

from datetime import datetime

from ..models import Execution, Span


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def money(value) -> float | None:
    return round(float(value), 6) if value is not None else None


def execution_dict(ex: Execution, project_ext: str | None = None, client_ext: str | None = None) -> dict:
    return {
        "id": ex.id,
        "trace_id": ex.trace_id,
        "workflow_id": ex.workflow_id,
        "session_id": ex.session_id,
        "project_id": project_ext,
        "client_id": client_ext,
        "workflow": ex.workflow_name,
        "workflow_version": ex.workflow_version,
        "status": ex.status,
        "error_kind": ex.root_error_kind,
        "error_message": ex.root_error_message,
        "metadata": ex.metadata_json,
        "started_at": iso(ex.started_at),
        "ended_at": iso(ex.ended_at),
        "duration_ms": round(ex.duration_ms, 2) if ex.duration_ms is not None else None,
        "total_cost": money(ex.total_cost),
        "unpriced_calls": ex.unpriced_calls,
        "cost_complete": ex.unpriced_calls == 0,
        "input_tokens": ex.input_tokens,
        "output_tokens": ex.output_tokens,
        "total_tokens": ex.total_tokens,
        "llm_calls": ex.llm_calls,
        "tool_calls": ex.tool_calls,
        "retrieval_calls": ex.retrieval_calls,
        "agent_calls": ex.agent_calls,
        "error_count": ex.error_count,
        "retry_count": ex.retry_count,
    }


def span_dict(sp: Span) -> dict:
    return {
        "id": sp.id,
        "span_id": sp.span_id,
        "parent_id": sp.parent_id,
        "kind": sp.kind,
        "name": sp.name,
        "status": sp.status,
        "error_type": sp.error_type,
        "error_message": sp.error_message,
        "error_kind": sp.error_kind,
        "started_at": iso(sp.started_at),
        "ended_at": iso(sp.ended_at),
        "duration_ms": round(sp.duration_ms, 2) if sp.duration_ms is not None else None,
        "llm_model": sp.llm_model,
        "llm_provider": sp.llm_provider,
        "input_tokens": sp.input_tokens,
        "output_tokens": sp.output_tokens,
        "total_tokens": sp.total_tokens,
        "tool_name": sp.tool_name,
        "retrieval_doc_count": sp.retrieval_doc_count,
        "retry_count": sp.retry_count,
        "cost": money(sp.cost),
        "attributes": sp.attributes,
    }