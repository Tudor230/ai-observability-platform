"""Helpers for reading flat, dot-namespaced OpenInference/OTel attributes."""
from __future__ import annotations

import json

from .ingest.otlp import RawSpan

OI_KIND = "openinference.span.kind"
SESSION_ID = "session.id"
USER_ID = "user.id"
METADATA = "metadata"

SDK_CLIENT_ID = "sdk.client_id"
SDK_PROJECT_ID = "sdk.project_id"
SDK_WORKFLOW_ID = "sdk.workflow_id"
SDK_WORKFLOW_VERSION = "sdk.workflow.version"
SDK_ERROR_TYPE = "sdk.error.type"
SDK_ERROR_MESSAGE = "sdk.error.message"
SDK_ERROR_KIND = "sdk.error.kind"
SDK_RETRY_COUNT = "sdk.retry.count"
SDK_RETRY_OF = "sdk.retry.of"

LLM_MODEL = "llm.model_name"
LLM_PROVIDER = "llm.provider"
LLM_PROMPT_TOKENS = "llm.token_count.prompt"
LLM_COMPLETION_TOKENS = "llm.token_count.completion"
LLM_TOTAL_TOKENS = "llm.token_count.total"
TOOL_NAME = "tool.name"

EXCEPTION_TYPE = "exception.type"
EXCEPTION_MESSAGE = "exception.message"

KIND_LLM = "LLM"
KIND_CHAIN = "CHAIN"
KIND_AGENT = "AGENT"
KIND_TOOL = "TOOL"
KIND_RETRIEVER = "RETRIEVER"
KIND_EMBEDDING = "EMBEDDING"
KIND_RERANKER = "RERANKER"
KIND_UNKNOWN = "UNKNOWN"

BILLABLE_KINDS = {KIND_LLM}


def get(attrs: dict[str, object], key: str, default=None):
    return attrs.get(key, default)


def as_str(attrs: dict[str, object], key: str) -> str | None:
    value = attrs.get(key)
    if value is None:
        return None
    return str(value)


def as_int(attrs: dict[str, object], key: str) -> int:
    value = attrs.get(key)
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def as_float(attrs: dict[str, object], key: str) -> float | None:
    value = attrs.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
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
        if event.get("name") == "exception":
            attrs = event.get("attributes", {})
            out.append(
                {
                    "type": as_str(attrs, EXCEPTION_TYPE),
                    "message": as_str(attrs, EXCEPTION_MESSAGE),
                }
            )
    return out


def retry_count(attrs: dict[str, object]) -> int:
    return as_int(attrs, SDK_RETRY_COUNT)


def retrieval_doc_count(span: RawSpan) -> int | None:
    """Count indexed retrieval.document entries (flattened keys like retrieval.documents.0.document.id)."""
    indexes = set()
    prefix = "retrieval.documents."
    for key in span.attributes:
        if key.startswith(prefix):
            rest = key[len(prefix) :]
            idx = rest.split(".", 1)[0]
            if idx.isdigit():
                indexes.add(int(idx))
    return len(indexes) or None