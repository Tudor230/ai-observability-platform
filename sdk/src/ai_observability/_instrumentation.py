"""Framework instrumentation wiring (LangChain + LlamaIndex instrumentors).

Reuses the OpenInference instrumentors with the SDK-owned TracerProvider.
Never double-instrument: warn at init when another instrumentor is active.
Payload capture is left ON at the instrumentor level; the enrichment layer
enforces the SDK's opt-in ``capture_prompts`` policy at export time (that is
the only way to support per-workflow overrides in both directions).
"""

from __future__ import annotations

import logging
from typing import Optional

from opentelemetry.sdk.trace import TracerProvider

from ._langgraph import (
    _already_instrumented_langgraph,
    instrument_langgraph,
    uninstrument_langgraph,
)

logger = logging.getLogger(__name__)

_langchain_instrumentor: Optional[object] = None
_llamaindex_instrumentor: Optional[object] = None


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


def instrument_frameworks(provider: TracerProvider) -> None:
    _instrument_langchain(provider)
    _instrument_llamaindex(provider)
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
    _langchain_instrumentor = LangChainInstrumentor()
    _langchain_instrumentor.instrument(
        tracer_provider=provider,
        # NOTE: separate_trace_from_runtime_context stays OFF so framework
        # spans parent into the manual workflow root via OTel context. The
        # plan's background-worker mode (§8) is deferred.
    )


def _instrument_llamaindex(provider: TracerProvider) -> None:
    global _llamaindex_instrumentor
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
    _llamaindex_instrumentor = LlamaIndexInstrumentor()
    _llamaindex_instrumentor.instrument(
        tracer_provider=provider,
    )


def uninstrument_frameworks() -> None:
    global _langchain_instrumentor, _llamaindex_instrumentor
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
    uninstrument_langgraph()