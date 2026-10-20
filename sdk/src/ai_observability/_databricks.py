"""Databricks AI Search (formerly Vector Search) auto-instrumentation.

OpenInference ships no Databricks instrumentor, so the SDK owns a minimal one:
a wrapt wrapper around the AI Search index query methods. It emits an
OpenInference **RETRIEVER** span with the query text, index identity, result
count, and the returned rows as ``retrieval.documents.*``. Both the canonical
``databricks.ai_search`` classes and the legacy ``databricks.vector_search``
package are covered when installed; failures record the exception + ERROR
status and re-raise unchanged.

Payload capture follows the SDK-wide policy: the wrapper always records the
query text and returned rows; the enrichment layer strips those payload
attributes at export when ``capture_prompts`` is off
(``databricks.ai_search.result_count`` survives).
"""

from __future__ import annotations

import importlib
import inspect
import json
import logging
from collections.abc import Mapping, Sequence
from typing import Any

import wrapt
from aiobs_contracts import KIND_RETRIEVER, RETRIEVAL_DOCUMENTS
from opentelemetry import trace as trace_api
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import SpanKind, Status, StatusCode

from ._attributes import (
    DOCUMENT_CONTENT,
    INPUT_MIME_TYPE,
    INPUT_VALUE,
    OI_SPAN_KIND,
    OUTPUT_MIME_TYPE,
    OUTPUT_VALUE,
)
from ._context import langchain_parent_context

logger = logging.getLogger(__name__)

_SPAN_NAME = "databricks.ai_search.query"
_TEXT_MIME = "text/plain"
_JSON_MIME = "application/json"

_DB_SYSTEM = "db.system"
_DB_OPERATION = "db.operation"
_DB_COLLECTION_NAME = "db.collection.name"
_DB_SYSTEM_VALUE = "databricks"
_QUERY_OPERATION = "query"

_ENDPOINT = "databricks.ai_search.endpoint"
_QUERY_TYPE = "databricks.ai_search.query_type"
_N_RESULTS = "databricks.ai_search.num_results"
_RESULT_COUNT = "databricks.ai_search.result_count"
_COLUMNS = "databricks.ai_search.columns"
_FILTERS = "databricks.ai_search.filters"
_SCORE_THRESHOLD = "databricks.ai_search.score_threshold"
_QUERY_VECTOR_DIM = "databricks.ai_search.query_vector_dimension"

_DOCUMENT_ID = "document.id"
_DOCUMENT_SCORE = "document.score"
_DOCUMENT_METADATA = "document.metadata"

_ID_KEYS = frozenset(
    {"id", "primary_key", "pk", "doc_id", "document_id", "chunk_id"}
)
_CONTENT_KEYS = frozenset(
    {"content", "text", "document", "page_content", "chunk", "body", "description"}
)
_SCORE_KEYS = frozenset({"score", "_score", "similarity", "distance", "relevance"})

_tracer: trace_api.Tracer | None = None
_instrumented = False
_wrapped: list[tuple[type, Any]] = []


# --- instrumentation surface ---------------------------------------------------


def instrument_databricks(provider: TracerProvider) -> None:
    """Patch AI Search ``similarity_search`` methods (idempotent)."""
    global _tracer, _instrumented
    if _instrumented:
        return
    classes = _index_classes()
    if not classes:
        return
    _tracer = provider.get_tracer("ai_observability")
    for cls in classes:
        _wrap_similarity_search(cls)
    _instrumented = True


def uninstrument_databricks() -> None:
    """Restore the original AI Search query methods (idempotent)."""
    global _tracer, _instrumented
    if not _instrumented:
        return
    for owner, original in _wrapped:
        current = owner.__dict__.get("similarity_search")
        if isinstance(current, wrapt.FunctionWrapper):
            owner.similarity_search = original  # type: ignore[attr-defined]
    _wrapped.clear()
    _instrumented = False
    _tracer = None


def already_instrumented_databricks() -> bool:
    """True when an AI Search query method is already wrapped."""
    for cls in _index_classes():
        owner = _method_owner(cls)
        if owner is not None and isinstance(
            owner.__dict__.get("similarity_search"), wrapt.FunctionWrapper
        ):
            return True
    return False


def _index_classes() -> list[type]:
    """Canonical AI Search classes plus the legacy Vector Search aliases."""
    found = [
        _load_class("databricks.ai_search.index", "AISearchIndex"),
        _load_class("databricks.ai_search.async_index", "AsyncAISearchIndex"),
        _load_class("databricks.vector_search.index", "VectorSearchIndex"),
        _load_class("databricks.vector_search.async_index", "AsyncVectorSearchIndex"),
    ]
    classes: list[type] = []
    for cls in found:
        if cls is not None and cls not in classes:
            classes.append(cls)
    return classes


def _load_class(module_name: str, class_name: str) -> type | None:
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        return None
    except Exception:
        logger.debug(
            "Databricks AI Search import failed for %s", module_name, exc_info=True
        )
        return None
    cls = getattr(module, class_name, None)
    return cls if isinstance(cls, type) else None


def _method_owner(cls: type) -> type | None:
    """The class that defines ``similarity_search`` (so the right dict is patched)."""
    for klass in cls.__mro__:
        if "similarity_search" in klass.__dict__:
            return klass
    return None


def _wrap_similarity_search(cls: type) -> None:
    owner = _method_owner(cls)
    if owner is None:
        return
    original = owner.__dict__.get("similarity_search")
    if original is None or isinstance(original, wrapt.FunctionWrapper):
        return
    wrapper = (
        _async_query_wrapper
        if inspect.iscoroutinefunction(original)
        else _query_wrapper
    )
    owner.similarity_search = wrapt.FunctionWrapper(  # type: ignore[attr-defined]
        original, wrapper
    )
    _wrapped.append((owner, original))


# --- span emission -------------------------------------------------------------


def _query_wrapper(wrapped, instance, args, kwargs):
    tracer = _tracer
    if tracer is None:
        return wrapped(*args, **kwargs)
    with tracer.start_as_current_span(
        _SPAN_NAME,
        context=langchain_parent_context(),
        kind=SpanKind.INTERNAL,
    ) as span:
        _set_request_attributes(span, instance, wrapped, args, kwargs)
        # Failures propagate: the span context manager records the exception
        # event and sets ERROR status (OTel defaults), then the error re-raises.
        result = wrapped(*args, **kwargs)
        _set_result_attributes(span, wrapped, instance, args, kwargs, result)
        span.set_status(Status(StatusCode.OK))
        return result


async def _async_query_wrapper(wrapped, instance, args, kwargs):
    tracer = _tracer
    if tracer is None:
        return await wrapped(*args, **kwargs)
    with tracer.start_as_current_span(
        _SPAN_NAME,
        context=langchain_parent_context(),
        kind=SpanKind.INTERNAL,
    ) as span:
        _set_request_attributes(span, instance, wrapped, args, kwargs)
        result = await wrapped(*args, **kwargs)
        _set_result_attributes(span, wrapped, instance, args, kwargs, result)
        span.set_status(Status(StatusCode.OK))
        return result


def _set_request_attributes(
    span: trace_api.Span, instance: Any, wrapped, args: tuple, kwargs: dict
) -> None:
    try:
        span.set_attributes(_request_attributes(instance, wrapped, args, kwargs))
    except Exception:
        logger.exception("Databricks AI Search request attributes failed")


def _set_result_attributes(
    span: trace_api.Span,
    wrapped,
    instance: Any,
    args: tuple,
    kwargs: dict,
    result: Any,
) -> None:
    try:
        span.set_attributes(_result_attributes(wrapped, instance, args, kwargs, result))
    except Exception:
        logger.exception("Databricks AI Search result attributes failed")


def _request_attributes(
    instance: Any, wrapped, args: tuple, kwargs: dict
) -> dict[str, Any]:
    params = _bound_parameters(wrapped, instance, args, kwargs)
    attrs: dict[str, Any] = {
        OI_SPAN_KIND: KIND_RETRIEVER,
        _DB_SYSTEM: _DB_SYSTEM_VALUE,
        _DB_OPERATION: _QUERY_OPERATION,
    }

    name = getattr(instance, "name", None)
    if isinstance(name, str) and name:
        attrs[_DB_COLLECTION_NAME] = name
    endpoint = getattr(instance, "endpoint_name", None)
    if isinstance(endpoint, str) and endpoint:
        attrs[_ENDPOINT] = endpoint

    query_text = params.get("query_text")
    if isinstance(query_text, str) and query_text:
        attrs[INPUT_VALUE] = query_text
        attrs[INPUT_MIME_TYPE] = _TEXT_MIME

    query_vector = params.get("query_vector")
    if isinstance(query_vector, Sequence) and not isinstance(
        query_vector, (str, bytes, bytearray)
    ):
        attrs[_QUERY_VECTOR_DIM] = len(query_vector)

    query_type = params.get("query_type")
    if isinstance(query_type, str) and query_type:
        attrs[_QUERY_TYPE] = query_type

    n_results = params.get("num_results")
    if isinstance(n_results, int) and not isinstance(n_results, bool):
        attrs[_N_RESULTS] = n_results

    columns = params.get("columns")
    if isinstance(columns, (list, tuple)) and columns:
        attrs[_COLUMNS] = json.dumps([str(column) for column in columns])

    filters = params.get("filters")
    if filters is not None:
        attrs[_FILTERS] = json.dumps(filters, default=str, ensure_ascii=False)

    score_threshold = params.get("score_threshold")
    if _is_number(score_threshold):
        attrs[_SCORE_THRESHOLD] = float(score_threshold)
    return attrs


def _result_attributes(
    wrapped, instance: Any, args: tuple, kwargs: dict, result: Any
) -> dict[str, Any]:
    if not isinstance(result, Mapping):
        return {}
    payload = result.get("result")
    if not isinstance(payload, Mapping):
        payload = result

    rows = payload.get("data_array") or []
    if not isinstance(rows, (list, tuple)):
        return {}
    requested = _bound_parameters(wrapped, instance, args, kwargs).get("columns")
    columns = _column_names(result, requested)

    attrs: dict[str, Any] = {}
    output_documents: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if isinstance(row, Mapping):
            record = dict(row)
        else:
            values = list(row) if isinstance(row, (list, tuple)) else [row]
            record = dict(zip(_row_names(columns, values), values))
        document = _document(record, index)
        prefix = f"{RETRIEVAL_DOCUMENTS}.{index}"
        if "id" in document:
            attrs[f"{prefix}.{_DOCUMENT_ID}"] = document["id"]
        if "content" in document:
            attrs[f"{prefix}.{DOCUMENT_CONTENT}"] = document["content"]
        if "metadata" in document:
            attrs[f"{prefix}.{_DOCUMENT_METADATA}"] = json.dumps(
                document["metadata"], default=str, ensure_ascii=False
            )
        if "score" in document:
            attrs[f"{prefix}.{_DOCUMENT_SCORE}"] = document["score"]
        output_documents.append(document)

    attrs[_RESULT_COUNT] = len(output_documents)
    if output_documents:
        attrs[OUTPUT_VALUE] = json.dumps(
            output_documents, default=str, ensure_ascii=False
        )
        attrs[OUTPUT_MIME_TYPE] = _JSON_MIME
    return attrs


def _column_names(result: Mapping, requested: Any) -> list[str]:
    manifest = result.get("manifest")
    if isinstance(manifest, Mapping):
        raw_columns = manifest.get("columns")
        if isinstance(raw_columns, list):
            names = []
            for column in raw_columns:
                if isinstance(column, Mapping):
                    name = column.get("name")
                else:
                    name = column
                if isinstance(name, str) and name:
                    names.append(name)
            if names:
                return names
    if isinstance(requested, (list, tuple)):
        return [str(column) for column in requested]
    return []


def _row_names(columns: list[str], values: list[Any]) -> list[str]:
    names = list(columns)
    if len(names) == len(values) - 1 and _is_number(values[-1]):
        # AI Search returns the relevance score as an extra trailing column
        # when it is not part of the requested projection.
        names.append("score")
    while len(names) < len(values):
        names.append(f"column_{len(names)}")
    return names[: len(values)]


def _document(record: Mapping[str, Any], index: int) -> dict[str, Any]:
    id_name, id_value = _pick(record, _ID_KEYS)
    score_name, score_value = _pick(record, _SCORE_KEYS)
    content_name, content_value = _pick(record, _CONTENT_KEYS)

    document: dict[str, Any] = {
        "id": str(id_value) if id_value is not None else str(index)
    }
    if content_name is not None:
        document["content"] = _stringify(content_value)
        metadata = {
            key: value
            for key, value in record.items()
            if key not in {id_name, score_name, content_name}
        }
    else:
        metadata = {
            key: value
            for key, value in record.items()
            if key not in {id_name, score_name}
        }
        document["content"] = json.dumps(metadata, default=str, ensure_ascii=False)
    if metadata:
        document["metadata"] = metadata
    if _is_number(score_value):
        document["score"] = float(score_value)
    return document


def _pick(record: Mapping[str, Any], keys: frozenset[str]) -> tuple[Any, Any]:
    for key, value in record.items():
        if str(key).lower() in keys and value is not None:
            return key, value
    return None, None


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str, ensure_ascii=False)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _bound_parameters(
    wrapped, instance: Any, args: tuple, kwargs: dict
) -> dict[str, Any]:
    """Call arguments keyed by parameter name (positional calls included)."""
    try:
        signature = inspect.signature(wrapped)
        first = next(iter(signature.parameters), None)
        if first in {"self", "cls"}:
            bound = signature.bind(instance, *args, **kwargs)
        else:
            bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        params = dict(bound.arguments)
        if first in {"self", "cls"}:
            params.pop(first, None)
        return params
    except (TypeError, ValueError):
        return dict(kwargs)
