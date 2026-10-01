"""ChromaDB client auto-instrumentation for raw ``chromadb`` usage.

OpenInference ships no ChromaDB instrumentor (and its OpenLLMetry bridge does
not convert Chroma spans), so the SDK owns a minimal one: a wrapt wrapper
around ``Collection.query`` that emits an OpenInference **RETRIEVER** span —
query text as ``input.value``, hits as ``retrieval.documents.*``
(id/content/metadata/distance), ``db.system``/``db.operation``/
``db.collection.name`` — nested under the active workflow root. Failed queries
record the exception + ERROR status and re-raise unchanged.

Payload capture follows the SDK-wide policy: the wrapper always records the
query text and documents; the enrichment layer strips those payload
attributes at export when ``capture_prompts`` is off
(``chroma.query.result_count`` survives). ``init()`` installs the wrapper
before the app queries; ``uninstrument_chroma`` restores the client.

Coverage (v1) is the sync ``Collection.query`` retrieval path only; ingestion
(``add``/``upsert``/``get``) and the async client are not instrumented.
"""

from __future__ import annotations

import inspect
import json
import logging
from collections.abc import Mapping
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

logger = logging.getLogger(__name__)

_SPAN_NAME = "chroma.query"
_TEXT_MIME = "text/plain"
_JSON_MIME = "application/json"

_DB_SYSTEM = "db.system"
_DB_OPERATION = "db.operation"
_DB_COLLECTION_NAME = "db.collection.name"
_N_RESULTS = "chroma.query.n_results"
_RESULT_COUNT = "chroma.query.result_count"
_INCLUDE = "chroma.query.include"
_WHERE = "chroma.query.where"

_DOCUMENT_ID = "document.id"
_DOCUMENT_SCORE = "document.score"
_DOCUMENT_METADATA = "document.metadata"

# ``db.system`` is a standard OTel semantic-convention value; ``chroma.query.*``
# metrics are SDK-local (kept out of the shared contracts because the backend
# does not parse them — they surface raw in the UI).
_DB_SYSTEM_VALUE = "chroma"
_QUERY_OPERATION = "query"

_tracer: trace_api.Tracer | None = None
_instrumented = False


# --- instrumentation surface ---------------------------------------------------


def instrument_chroma(provider: TracerProvider) -> None:
    """Patch sync ``Collection.query`` to emit RETRIEVER spans (idempotent)."""
    global _tracer, _instrumented
    if _instrumented:
        return
    from chromadb.api.models.Collection import Collection

    _tracer = provider.get_tracer("ai_observability")
    _wrap_query(Collection)
    _instrumented = True


def uninstrument_chroma() -> None:
    """Restore the original ``Collection.query`` (idempotent)."""
    global _tracer, _instrumented
    if not _instrumented:
        return
    try:
        from chromadb.api.models.Collection import Collection
    except ImportError:
        _instrumented = False
        _tracer = None
        return
    owner = _query_owner(Collection)
    if owner is not None:
        current = owner.__dict__.get("query")
        if isinstance(current, wrapt.FunctionWrapper):
            owner.query = current.__wrapped__
    _instrumented = False
    _tracer = None


def _wrap_query(cls: type) -> None:
    owner = _query_owner(cls)
    if owner is None:
        return
    original = owner.__dict__.get("query")
    if original is None or isinstance(original, wrapt.FunctionWrapper):
        return
    owner.query = wrapt.FunctionWrapper(original, _query_wrapper)


def _query_owner(cls: type) -> type | None:
    """The class that defines ``query`` (so the right ``__dict__`` is patched)."""
    for klass in cls.__mro__:
        if "query" in klass.__dict__:
            return klass
    return None


# --- span emission -------------------------------------------------------------


def _query_wrapper(wrapped, instance, args, kwargs):
    tracer = _tracer
    if tracer is None:
        return wrapped(*args, **kwargs)
    with tracer.start_as_current_span(_SPAN_NAME, kind=SpanKind.INTERNAL) as span:
        span.set_attributes(_request_attributes(instance, wrapped, args, kwargs))
        # Failures propagate: the span context manager records the exception
        # event and sets ERROR status (OTel defaults), then the error re-raises.
        result = wrapped(*args, **kwargs)
        span.set_attributes(_result_attributes(result))
        span.set_status(Status(StatusCode.OK))
        return result


def _request_attributes(instance: Any, wrapped, args: tuple, kwargs: dict) -> dict[str, Any]:
    params = _bound_parameters(wrapped, instance, args, kwargs)
    attrs: dict[str, Any] = {
        OI_SPAN_KIND: KIND_RETRIEVER,
        _DB_SYSTEM: _DB_SYSTEM_VALUE,
        _DB_OPERATION: _QUERY_OPERATION,
    }
    name = getattr(instance, "name", None)
    if isinstance(name, str) and name:
        attrs[_DB_COLLECTION_NAME] = name

    texts = _query_texts(params)
    if texts:
        if len(texts) == 1:
            attrs[INPUT_VALUE] = texts[0]
            attrs[INPUT_MIME_TYPE] = _TEXT_MIME
        else:
            attrs[INPUT_VALUE] = json.dumps(texts, ensure_ascii=False)
            attrs[INPUT_MIME_TYPE] = _JSON_MIME

    n_results = params.get("n_results")
    if isinstance(n_results, int) and not isinstance(n_results, bool):
        attrs[_N_RESULTS] = n_results
    include = params.get("include")
    if isinstance(include, (list, tuple)) and include:
        attrs[_INCLUDE] = json.dumps([str(item) for item in include])
    where = params.get("where")
    if where:
        attrs[_WHERE] = json.dumps(where, default=str)
    return attrs


def _bound_parameters(wrapped, instance: Any, args: tuple, kwargs: dict) -> dict[str, Any]:
    """Call arguments keyed by parameter name (positional calls included)."""
    try:
        bound = inspect.signature(wrapped).bind(instance, *args, **kwargs)
    except (TypeError, ValueError):
        return dict(kwargs)
    return dict(bound.arguments)


def _query_texts(params: Mapping[str, Any]) -> list[str]:
    raw = params.get("query_texts")
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    try:
        return [str(text) for text in raw]
    except TypeError:
        return []


def _result_attributes(result: Any) -> dict[str, Any]:
    if not isinstance(result, Mapping):
        return {}
    ids = result.get("ids") or []
    documents = result.get("documents") or []
    metadatas = result.get("metadatas") or []
    distances = result.get("distances") or []

    attrs: dict[str, Any] = {}
    output_documents: list[dict[str, Any]] = []
    count = 0
    for query_index, query_ids in enumerate(ids):
        for result_index, doc_id in enumerate(query_ids or []):
            prefix = f"{RETRIEVAL_DOCUMENTS}.{count}"
            document: dict[str, Any] = {}
            if doc_id is not None:
                attrs[f"{prefix}.{_DOCUMENT_ID}"] = str(doc_id)
                document["id"] = str(doc_id)
            content = _at(documents, query_index, result_index)
            if content is not None:
                attrs[f"{prefix}.{DOCUMENT_CONTENT}"] = str(content)
                document["content"] = str(content)
            metadata = _at(metadatas, query_index, result_index)
            if metadata is not None:
                attrs[f"{prefix}.{_DOCUMENT_METADATA}"] = json.dumps(metadata, default=str)
                document["metadata"] = metadata
            distance = _at(distances, query_index, result_index)
            if isinstance(distance, (int, float)) and not isinstance(distance, bool):
                # Chroma returns distances (lower = closer); the OpenInference
                # document score slot is the only numeric relevance field, and
                # LangChain's Chroma wrapper records distances there too.
                attrs[f"{prefix}.{_DOCUMENT_SCORE}"] = float(distance)
                document["score"] = float(distance)
            output_documents.append(document)
            count += 1
    attrs[_RESULT_COUNT] = count
    if output_documents:
        # Upstream retriever spans (LangChain) carry the documents in
        # ``output.value`` too; generic viewers (dashboard Output tab, Phoenix
        # output) read that, so emit the same JSON shape alongside the
        # ``retrieval.documents.*`` attributes.
        attrs[OUTPUT_VALUE] = json.dumps(output_documents, default=str, ensure_ascii=False)
        attrs[OUTPUT_MIME_TYPE] = _JSON_MIME
    return attrs


def _at(values: Any, outer: int, inner: int) -> Any:
    """``values[outer][inner]`` when present (Chroma nests per query)."""
    try:
        return values[outer][inner]
    except (IndexError, KeyError, TypeError):
        return None
