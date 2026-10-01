"""Framework instrumentation wiring (LangChain + LlamaIndex + Ollama + ChromaDB).

Reuses the OpenInference instrumentors with the SDK-owned TracerProvider and
the SDK's own minimal ChromaDB interceptor (OpenInference has no ChromaDB
instrumentor). Never double-instrument: warn at init when another instrumentor
is active.

The instrumented packages (``langchain_core``, ``llama_index.core``,
``ollama``, ``chromadb``) are **optional**: each is skipped quietly (debug log)
when not importable. An instrumentor that fails for any other reason warns and
never propagates into ``init()`` (plan §8).

Payload capture is left ON at the instrumentor level; the enrichment layer
enforces the SDK's opt-in ``capture_prompts`` policy at export time (that is
the only way to support per-workflow overrides in both directions).
"""

from __future__ import annotations

import importlib.util
import logging
from typing import Optional

from opentelemetry.sdk.trace import TracerProvider

from ._chroma import instrument_chroma, uninstrument_chroma
from ._langgraph import (
    _already_instrumented_langgraph,
    instrument_langgraph,
    uninstrument_langgraph,
)

logger = logging.getLogger(__name__)

_langchain_instrumentor: Optional[object] = None
_llamaindex_instrumentor: Optional[object] = None
_ollama_instrumentor: Optional[object] = None


def _module_available(name: str) -> bool:
    """True when the (optional) framework package is importable."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _langchain_available() -> bool:
    return _module_available("langchain_core")


def _llamaindex_available() -> bool:
    return _module_available("llama_index.core")


def _ollama_available() -> bool:
    return _module_available("ollama")


def _chroma_available() -> bool:
    return _module_available("chromadb")


def _already_instrumented_langchain() -> bool:
    try:
        import langchain_core.callbacks
        import wrapt
    except ImportError:
        return False
    return isinstance(
        langchain_core.callbacks.BaseCallbackManager.__init__,
        (wrapt.ObjectProxy, wrapt.BoundFunctionWrapper),
    )


def _already_instrumented_llamaindex() -> bool:
    try:
        from llama_index.core.instrumentation import get_dispatcher
    except ImportError:
        return False
    dispatcher = get_dispatcher()
    for handler in dispatcher.event_handlers:
        if type(handler).__module__.startswith("openinference.instrumentation.llama_index"):
            return True
    return False


def _already_instrumented_ollama() -> bool:
    try:
        import wrapt
        from ollama._client import Client
    except ImportError:
        return False
    return isinstance(
        Client.chat,
        (wrapt.ObjectProxy, wrapt.BoundFunctionWrapper),
    )


def _already_instrumented_chroma() -> bool:
    """True when ``Collection.query`` is wrapped, by us or another instrumentor
    (e.g. Traceloop's ``opentelemetry-instrumentation-chromadb``)."""
    try:
        import wrapt
        from chromadb.api.models.Collection import Collection
    except ImportError:
        return False
    for klass in Collection.__mro__:
        if isinstance(klass.__dict__.get("query"), wrapt.FunctionWrapper):
            return True
    return False


def _safe_instrument(instrumentor: object, provider: TracerProvider, **kwargs) -> bool:
    """Instrument with the SDK provider; failures warn and never propagate (plan §8)."""
    try:
        instrumentor.instrument(tracer_provider=provider, **kwargs)
    except Exception:
        logger.warning(
            "%s failed; continuing without it",
            type(instrumentor).__name__,
            exc_info=True,
        )
        return False
    return True


def instrument_frameworks(provider: TracerProvider) -> None:
    _instrument_langchain(provider)
    _instrument_llamaindex(provider)
    _instrument_ollama(provider)
    _instrument_chroma(provider)
    _instrument_langgraph()


def _instrument_langgraph() -> None:
    """LangGraph boundary + HITL lifecycle interception (no OTel wiring —
    the LangChain instrumentor owns LangGraph node spans)."""
    if _already_instrumented_langgraph():
        logger.warning(
            "LangGraph is already instrumented; "
            "skipping to avoid double HITL capture."
        )
        return
    instrument_langgraph()


def _instrument_langchain(provider: TracerProvider) -> None:
    global _langchain_instrumentor
    if not _langchain_available():
        logger.debug("langchain-core is not installed; skipping LangChain instrumentation")
        return
    try:
        from openinference.instrumentation.langchain import LangChainInstrumentor
    except ImportError as error:
        logger.warning("LangChain instrumentor unavailable: %s", error)
        return
    if _already_instrumented_langchain():
        logger.warning(
            "LangChain is already instrumented by another instrumentor; "
            "skipping to avoid double instrumentation (nested spans, token undercount)."
        )
        return
    instrumentor = LangChainInstrumentor()
    # NOTE: separate_trace_from_runtime_context stays OFF so framework spans
    # parent into the manual workflow root via OTel context. The plan's
    # background-worker mode (§8) is deferred.
    if _safe_instrument(instrumentor, provider):
        _langchain_instrumentor = instrumentor


def _instrument_llamaindex(provider: TracerProvider) -> None:
    global _llamaindex_instrumentor
    if not _llamaindex_available():
        logger.debug("llama-index-core is not installed; skipping LlamaIndex instrumentation")
        return
    try:
        from openinference.instrumentation.llama_index import LlamaIndexInstrumentor
    except ImportError as error:
        logger.warning("LlamaIndex instrumentor unavailable: %s", error)
        return
    if _already_instrumented_llamaindex():
        logger.warning(
            "LlamaIndex is already instrumented by another instrumentor; "
            "skipping to avoid double instrumentation."
        )
        return
    instrumentor = LlamaIndexInstrumentor()
    if _safe_instrument(instrumentor, provider):
        _llamaindex_instrumentor = instrumentor


def _instrument_ollama(provider: TracerProvider) -> None:
    """Raw ``ollama`` client coverage (plan §7.4).

    The instrumentor must be active before the first chat call — the SDK calls
    it from ``init()``, i.e. at app startup, which satisfies that.
    """
    global _ollama_instrumentor
    if not _ollama_available():
        logger.debug("ollama is not installed; skipping Ollama instrumentation")
        return
    try:
        from openinference.instrumentation.ollama import OllamaInstrumentor
    except ImportError as error:
        logger.warning("Ollama instrumentor unavailable: %s", error)
        return
    if _already_instrumented_ollama():
        logger.warning(
            "Ollama is already instrumented by another instrumentor; "
            "skipping to avoid double instrumentation."
        )
        return
    instrumentor = OllamaInstrumentor()
    if _safe_instrument(instrumentor, provider):
        _ollama_instrumentor = instrumentor


def _instrument_chroma(provider: TracerProvider) -> None:
    """Raw ``chromadb`` client coverage (plan §7.5).

    The SDK owns this interceptor because OpenInference has no ChromaDB
    instrumentor; it wraps sync ``Collection.query`` before the app queries
    (``init()`` runs at startup).
    """
    if not _chroma_available():
        logger.debug("chromadb is not installed; skipping ChromaDB instrumentation")
        return
    if _already_instrumented_chroma():
        logger.warning(
            "ChromaDB is already instrumented by another instrumentor; "
            "skipping to avoid double instrumentation."
        )
        return
    try:
        instrument_chroma(provider)
    except Exception:
        logger.warning(
            "ChromaDB instrumentation failed; continuing without it", exc_info=True
        )


def uninstrument_frameworks() -> None:
    global _langchain_instrumentor, _llamaindex_instrumentor, _ollama_instrumentor
    if _langchain_instrumentor is not None:
        try:
            _langchain_instrumentor.uninstrument()
        except Exception:
            logger.exception("Failed to uninstrument LangChain")
        _langchain_instrumentor = None
    if _llamaindex_instrumentor is not None:
        try:
            _llamaindex_instrumentor.uninstrument()
        except Exception:
            logger.exception("Failed to uninstrument LlamaIndex")
        _llamaindex_instrumentor = None
    if _ollama_instrumentor is not None:
        try:
            _ollama_instrumentor.uninstrument()
        except Exception:
            logger.exception("Failed to uninstrument Ollama")
        _ollama_instrumentor = None
    uninstrument_chroma()
    uninstrument_langgraph()
