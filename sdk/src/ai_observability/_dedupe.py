"""Suppress raw-provider spans already covered by a framework LLM span.

LangChain chat models call the provider's raw Python client: ``ChatOllama``
invokes ``ollama.Client.chat`` and ``ChatGroq`` invokes
``groq.Completions.create``. The SDK instruments both layers, so one provider
request would otherwise export two LLM spans — the framework's ``ChatOllama`` /
``ChatGroq`` span and the raw ``Chat`` / ``Completions`` span.

The raw span is not even a child of the framework span: the OpenInference
LangChain tracer deliberately does not attach its spans to the OTel context,
so the raw instrumentor parents to the last manually attached span (usually the
workflow root). Both spans therefore look like concurrent LLM calls and the
backend counts the call, tokens and cost twice.

The guard below wraps the raw client entry points. When the current OTel trace
has an active LangChain **LLM** run, it sets OTel's suppression key for the
duration of the raw call, making the raw instrumentor a no-op. Raw calls made
inside non-LLM LangChain runs (tools/chains) and calls outside LangChain keep
their span.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from opentelemetry import context as context_api
from opentelemetry import trace as trace_api

logger = logging.getLogger(__name__)


def _langchain_llm_span_active() -> bool:
    """True when the current OTel trace has an active LangChain LLM run.

    ``get_current_span()`` from the LangChain instrumentor is not usable here:
    chat-model ``_generate``/``_stream`` methods do not see LangChain's
    ``var_child_runnable_config``. The instrumentor's run map does contain the
    active ``run_type == "llm"`` run, and its span carries the OTel trace id we
    need to match.
    """
    try:
        from openinference.instrumentation.langchain import LangChainInstrumentor

        instrumentor = LangChainInstrumentor()
        tracer = getattr(instrumentor, "_tracer", None)
        run_map = getattr(tracer, "run_map", None)
        if not run_map:
            return False
        current = trace_api.get_current_span().get_span_context()
        if not current.is_valid:
            return False
        try:
            runs = list(run_map.values())
        except RuntimeError:
            # The LangChain tracer updates the run map from callback threads.
            # Returning False (one possible duplicate span) is safer than
            # failing the application's provider call.
            return False
        for run in runs:
            if getattr(run, "run_type", None) != "llm":
                continue
            run_id = getattr(run, "id", None)
            if run_id is None:
                continue
            span = instrumentor.get_span(run_id)
            if span is None:
                continue
            if span.get_span_context().trace_id == current.trace_id:
                return True
    except Exception:  # noqa: BLE001 - optional/private integration probe
        logger.debug("LangChain LLM-run lookup failed", exc_info=True)
    return False


class _SyncGuard:
    """Callable wrapt wrapper for synchronous raw client methods."""

    def __call__(
        self,
        wrapped: Any,
        instance: Any,
        args: tuple[Any, ...],
        kwargs: Mapping[str, Any],
    ) -> Any:
        if not _langchain_llm_span_active():
            return wrapped(*args, **kwargs)
        token = context_api.attach(
            context_api.set_value(context_api._SUPPRESS_INSTRUMENTATION_KEY, True)
        )
        try:
            return wrapped(*args, **kwargs)
        finally:
            context_api.detach(token)


class _AsyncGuard:
    """Callable wrapt wrapper for asynchronous raw client methods."""

    async def __call__(
        self,
        wrapped: Any,
        instance: Any,
        args: tuple[Any, ...],
        kwargs: Mapping[str, Any],
    ) -> Any:
        if not _langchain_llm_span_active():
            return await wrapped(*args, **kwargs)
        token = context_api.attach(
            context_api.set_value(context_api._SUPPRESS_INSTRUMENTATION_KEY, True)
        )
        try:
            return await wrapped(*args, **kwargs)
        finally:
            context_api.detach(token)


def _wrap(module: str, name: str, wrapper: object) -> None:
    try:
        import wrapt

        wrapt.wrap_function_wrapper(module, name, wrapper)
    except Exception:  # noqa: BLE001 - guard is best effort, never breaks init
        logger.warning(
            "Failed to install duplicate-span guard on %s.%s",
            module,
            name,
            exc_info=True,
        )


def _rebind_module_level_ollama_chat() -> None:
    """``ollama.chat`` is bound at import time; route it through the guard."""
    try:
        import ollama

        client = getattr(ollama, "_client", None)
        chat = getattr(client, "chat", None)
        if chat is not None:
            ollama.chat = chat
    except Exception:  # noqa: BLE001 - optional integration
        logger.debug("Could not rebind ollama.chat through the guard", exc_info=True)


def suppress_duplicate_raw_spans(
    *, ollama: bool = False, groq: bool = False
) -> None:
    """Install guards after the SDK's raw Ollama/Groq instrumentors are active.

    Only call this for instrumentors the SDK installed itself: wrapping another
    library's instrumentor would make cleanup ownership ambiguous.
    """
    if ollama:
        _wrap("ollama._client", "Client.chat", _SyncGuard())
        _wrap("ollama._client", "AsyncClient.chat", _AsyncGuard())
        _rebind_module_level_ollama_chat()
    if groq:
        _wrap(
            "groq.resources.chat.completions",
            "Completions.create",
            _SyncGuard(),
        )
        _wrap(
            "groq.resources.chat.completions",
            "AsyncCompletions.create",
            _AsyncGuard(),
        )
