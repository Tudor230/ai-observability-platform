"""Helpers for reading flat, dot-namespaced OpenInference/OTel attributes.

Attribute names come from ``aiobs_contracts`` (the single source of truth shared
with the SDK); only reading helpers live here.
"""
from __future__ import annotations

import json

import aiobs_contracts as c

from .ingest.otlp import RawSpan

OI_KIND = c.OI_SPAN_KIND
SESSION_ID = c.SESSION_ID
USER_ID = c.USER_ID
METADATA = c.METADATA

SDK_CLIENT_ID = c.SDK_CLIENT_ID
SDK_PROJECT_ID = c.SDK_PROJECT_ID
SDK_WORKFLOW_ID = c.SDK_WORKFLOW_ID
SDK_WORKFLOW_VERSION = c.SDK_WORKFLOW_VERSION
SDK_ERROR_TYPE = c.SDK_ERROR_TYPE
SDK_ERROR_MESSAGE = c.SDK_ERROR_MESSAGE
SDK_ERROR_KIND = c.SDK_ERROR_KIND
SDK_RETRY_COUNT = c.SDK_RETRY_COUNT
SDK_RETRY_OF = c.SDK_RETRY_OF
SDK_TOKENS_ESTIMATED = c.SDK_TOKENS_ESTIMATED

LLM_MODEL = c.LLM_MODEL_NAME
LLM_PROVIDER = c.LLM_PROVIDER
LLM_PROMPT_TOKENS = c.LLM_TOKEN_COUNT_PROMPT
LLM_COMPLETION_TOKENS = c.LLM_TOKEN_COUNT_COMPLETION
LLM_TOTAL_TOKENS = c.LLM_TOKEN_COUNT_TOTAL
LLM_CACHE_READ_TOKENS = c.LLM_TOKEN_COUNT_PROMPT_CACHE_READ
LLM_CACHE_WRITE_TOKENS = c.LLM_TOKEN_COUNT_PROMPT_CACHE_WRITE
LLM_REASONING_TOKENS = c.LLM_TOKEN_COUNT_COMPLETION_REASONING
TOOL_NAME = c.TOOL_NAME

EXCEPTION_TYPE = c.EXCEPTION_TYPE
EXCEPTION_MESSAGE = c.EXCEPTION_MESSAGE

KIND_LLM = c.KIND_LLM
KIND_CHAIN = c.KIND_CHAIN
KIND_AGENT = c.KIND_AGENT
KIND_TOOL = c.KIND_TOOL
KIND_RETRIEVER = c.KIND_RETRIEVER
KIND_EMBEDDING = c.KIND_EMBEDDING
KIND_RERANKER = c.KIND_RERANKER
KIND_UNKNOWN = c.KIND_UNKNOWN


def get(attrs: dict[str, object], key: str, default=None):
    return attrs.get(key, default)


def as_str(attrs: dict[str, object], key: str) -> str | None:
    value = attrs.get(key)
    if value is None:
        return None
    return str(value)


def as_int(attrs: dict[str, object], key: str) -> int:
    value = attrs.get(key)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
    return 0


def as_float(attrs: dict[str, object], key: str) -> float | None:
    value = attrs.get(key)
    if isinstance(value, (int, float, str)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return None


def span_kind(span: RawSpan) -> str:
    kind = span.attributes.get(OI_KIND)
    if isinstance(kind, str):
        return kind.upper()
    return KIND_UNKNOWN


def metadata_dict(span: RawSpan) -> dict | None:
    value = span.attributes.get(METADATA)
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except (ValueError, TypeError):
            return None
    return None


def exception_events(span: RawSpan) -> list[dict]:
    out = []
    for event in span.events:
        if event.get("name") == c.EXCEPTION_EVENT_NAME:
            attrs = event.get("attributes", {})
            out.append(
                {
                    "type": as_str(attrs, c.EXCEPTION_TYPE),
                    "message": as_str(attrs, c.EXCEPTION_MESSAGE),
                }
            )
    return out


def real_exception_events(span: RawSpan) -> list[dict]:
    """Exception events excluding LangGraph control flow (interrupts/Commands).

    Mirrors the SDK: those exceptions pause execution, they are not failures.
    """
    return [
        event
        for event in exception_events(span)
        if not c.is_control_flow_exception(event.get("type"))
    ]


def retry_count(attrs: dict[str, object]) -> int:
    return as_int(attrs, SDK_RETRY_COUNT)


def retrieval_doc_count(span: RawSpan) -> int | None:
    """Count indexed retrieval.document entries (flattened keys like retrieval.documents.0.document.id)."""
    indexes = set()
    prefix = f"{c.RETRIEVAL_DOCUMENTS}."
    for key in span.attributes:
        if key.startswith(prefix):
            rest = key[len(prefix) :]
            idx = rest.split(".", 1)[0]
            if idx.isdigit():
                indexes.add(int(idx))
    return len(indexes) or None