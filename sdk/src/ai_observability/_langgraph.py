"""LangGraph human-in-the-loop auto-interception.

LangGraph itself is traced by the OpenInference LangChain instrumentor (it is
built on ``langchain-core``): each node run is a CHAIN/AGENT span carrying
LangGraph's ``metadata.langgraph_node``. The instrumentor does NOT capture the
interrupt payload or the resume value — those exist only in the LangGraph
runtime (``result["__interrupt__"]``, ``Command(resume=...)``, stream marker
chunks, and the ``GraphCallbackHandler`` lifecycle events). This module
captures them automatically and records ``sdk.hitl.*`` attributes for the
enrichment layer to stamp on the workflow root.

Two mechanisms (ticket 02):

* **Boundary patch** — wrapt-wraps ``Pregel.invoke/ainvoke/stream/astream``.
  The wrapper is a strict pass-through (same return, same exceptions) and
  records the resume value from a ``Command`` input and the interrupt payload
  from ``__interrupt__`` output/stream chunks. Works on any LangGraph version.
* **Lifecycle hook** — patches ``get_sync/async_graph_callback_manager_for_config``
  to inject an SDK ``GraphCallbackHandler`` (langgraph >= 1.1.9) whose
  ``on_interrupt``/``on_resume`` record the typed payloads plus checkpoint id
  and (best-effort) the interrupting node name.

Records go into ``state.hitl`` keyed by the current OTel ``(trace_id,
root_span_id)``; the enrichment layer consumes them with ``take`` when each
workflow root completes. First writer wins, so the boundary patch and the
lifecycle hook dedup. The compound key lets an interrupt run and its resume run
share one ``trace_id`` (see ``_ids``) while each stamps its own root.
"""

from __future__ import annotations

import inspect
import json
import logging
from typing import Any, Optional

import wrapt
from opentelemetry import trace as trace_api

from ._attributes import (
    SDK_HITL_CHECKPOINT_ID,
    SDK_HITL_INTERRUPT_PAYLOAD,
    SDK_HITL_INTERRUPTED,
    SDK_HITL_RESUME_VALUE,
    SDK_HITL_RESUMED,
    SDK_HITL_THREAD_ID,
)
from ._state import get_state

logger = logging.getLogger(__name__)

_TRUE = "true"
_FALSE = "false"

_PREGEL_METHODS = ("invoke", "ainvoke", "stream", "astream")
_LIFECYCLE_HOOK_FNS = (
    "get_sync_graph_callback_manager_for_config",
    "get_async_graph_callback_manager_for_config",
)

_instrumented = False


# --- public instrumentation surface --------------------------------------------


def instrument_langgraph() -> None:
    """Patch the LangGraph graph boundary + lifecycle hooks (idempotent)."""
    global _instrumented
    if _instrumented:
        return
    try:
        from langgraph.pregel import Pregel
    except ImportError as error:
        logger.warning("LangGraph instrumentation unavailable: %s", error)
        return
    try:
        for name in _PREGEL_METHODS:
            _wrap_pregel_method(Pregel, name)
        _patch_lifecycle_hooks()
        _instrumented = True
    except Exception:
        logger.exception("LangGraph instrumentation failed")


def uninstrument_langgraph() -> None:
    global _instrumented
    if not _instrumented:
        return
    try:
        from langgraph.pregel import Pregel
    except ImportError:
        _instrumented = False
        return
    for name in _PREGEL_METHODS:
        current = Pregel.__dict__.get(name)
        if isinstance(current, wrapt.FunctionWrapper):
            setattr(Pregel, name, current.__wrapped__)
    try:
        from langgraph import callbacks as lg_callbacks
        from langgraph.pregel import main as lg_pregel_main
    except ImportError:
        pass
    else:
        for module in (lg_callbacks, lg_pregel_main):
            for name in _LIFECYCLE_HOOK_FNS:
                fn = getattr(module, name, None)
                if isinstance(fn, wrapt.FunctionWrapper):
                    setattr(module, name, fn.__wrapped__)
    _instrumented = False


def _already_instrumented_langgraph() -> bool:
    return _instrumented


# --- recording -----------------------------------------------------------------


def _record_hitl(**attrs: str) -> None:
    """Record pending sdk.hitl.* attributes for the current execution."""
    ctx = trace_api.get_current_span().get_span_context()
    if not ctx.is_valid:
        return
    get_state().hitl.record((ctx.trace_id, ctx.span_id), **attrs)


class _Recorder:
    def __init__(self, *, thread_id: Optional[str], resume_value: Optional[str]) -> None:
        self._thread_id = thread_id
        self._resume_value = resume_value
        self._resume_emitted = False

    def process_result(self, result: Any) -> None:
        interrupts = _interrupts_from_result(result)
        if interrupts is not None:
            self._emit_interrupt(interrupts)
        else:
            self._emit_resume()

    def _emit_interrupt(self, interrupts) -> None:
        attrs = {
            SDK_HITL_INTERRUPTED: _TRUE,
            SDK_HITL_INTERRUPT_PAYLOAD: _interrupts_json(interrupts),
        }
        self._with_thread(attrs)
        _record_hitl(**attrs)

    def _emit_resume(self) -> None:
        if self._resume_value is None or self._resume_emitted:
            return
        self._resume_emitted = True
        attrs = {
            SDK_HITL_INTERRUPTED: _FALSE,
            SDK_HITL_RESUMED: _TRUE,
            SDK_HITL_RESUME_VALUE: self._resume_value,
        }
        self._with_thread(attrs)
        _record_hitl(**attrs)

    def _with_thread(self, attrs: dict) -> None:
        if self._thread_id is not None:
            attrs.setdefault(SDK_HITL_THREAD_ID, self._thread_id)


# --- boundary patch ------------------------------------------------------------


def _wrap_pregel_method(cls: type, name: str) -> None:
    original = cls.__dict__.get(name)
    if original is None or isinstance(original, wrapt.FunctionWrapper):
        return
    setattr(cls, name, wrapt.FunctionWrapper(original, _make_boundary_wrapper(name)))


def _make_boundary_wrapper(method_name: str):
    def wrapper(wrapped, instance, args, kwargs):
        input_value, config = _extract_input_and_config(args, kwargs)
        recorder = _Recorder(
            thread_id=_extract_thread_id(config),
            resume_value=_extract_resume_value(input_value),
        )
        result = wrapped(*args, **kwargs)
        if inspect.iscoroutine(result):
            return _wrap_coroutine(result, recorder)
        if inspect.isasyncgen(result):
            return _wrap_asyncgen(result, recorder)
        if method_name == "stream":
            return _wrap_syncgen(result, recorder)
        recorder.process_result(result)
        return result

    return wrapper


def _wrap_coroutine(coro, recorder):
    async def _run():
        result = await coro
        recorder.process_result(result)
        return result

    return _run()


def _wrap_syncgen(gen, recorder):
    for chunk in gen:
        recorder.process_result(chunk)
        yield chunk


def _wrap_asyncgen(agen, recorder):
    async def _run():
        async for chunk in agen:
            recorder.process_result(chunk)
            yield chunk

    return _run()


def _extract_input_and_config(args, kwargs) -> tuple[Any, Optional[dict]]:
    input_value = kwargs.get("input")
    config = kwargs.get("config")
    if "input" not in kwargs and args:
        input_value = args[0]
    if "config" not in kwargs and args and len(args) > 1:
        config = args[1]
    return input_value, config


def _extract_thread_id(config) -> Optional[str]:
    if config is None:
        return None
    try:
        configurable = config.get("configurable")
        if isinstance(configurable, dict):
            thread_id = configurable.get("thread_id")
            if thread_id is not None:
                return str(thread_id)
    except Exception:
        pass
    return None


def _extract_resume_value(input_value) -> Optional[str]:
    try:
        from langgraph.types import Command
    except ImportError:
        return None
    if isinstance(input_value, Command):
        resume = getattr(input_value, "resume", None)
        if resume is not None:
            return _safe_json(resume)
    return None


def _interrupts_from_result(result: Any):
    if isinstance(result, dict):
        return result.get("__interrupt__")
    return None


def _interrupts_json(interrupts) -> str:
    values = [getattr(interrupt, "value", interrupt) for interrupt in interrupts]
    return _safe_json(values)


def _safe_json(value: Any) -> str:
    return json.dumps(value, default=str)


# --- lifecycle hook ------------------------------------------------------------


def _patch_lifecycle_hooks() -> None:
    try:
        from langgraph import callbacks as lg_callbacks
        from langgraph.pregel import main as lg_pregel_main
    except ImportError:
        return
    handler_cls = getattr(lg_callbacks, "GraphCallbackHandler", None)
    if handler_cls is None:
        return
    hitl_handler_cls = _make_lifecycle_handler(handler_cls)
    # Patch both the definition site (for modules imported later) and the
    # call site module (``langgraph.pregel.main`` binds the function at import
    # time, so re-patching its module global is what actually takes effect).
    for module in (lg_callbacks, lg_pregel_main):
        for name in _LIFECYCLE_HOOK_FNS:
            fn = getattr(module, name, None)
            if fn is None or isinstance(fn, wrapt.FunctionWrapper):
                continue
            setattr(
                module,
                name,
                wrapt.FunctionWrapper(fn, _hook_injector(hitl_handler_cls)),
            )


def _hook_injector(handler_cls):
    def wrapper(wrapped, instance, args, kwargs):
        manager = wrapped(*args, **kwargs)
        try:
            manager.handlers.append(handler_cls())
        except Exception:
            pass
        return manager

    return wrapper


def _make_lifecycle_handler(handler_cls):
    class _HITLLifecycleHandler(handler_cls):
        def on_interrupt(self, event: Any) -> None:
            attrs = {SDK_HITL_INTERRUPTED: _TRUE}
            interrupts = getattr(event, "interrupts", None)
            if interrupts:
                attrs[SDK_HITL_INTERRUPT_PAYLOAD] = _interrupts_json(interrupts)
            _record_hitl(**attrs)

        def on_resume(self, event: Any) -> None:
            attrs = {SDK_HITL_INTERRUPTED: _FALSE}
            checkpoint_id = getattr(event, "checkpoint_id", None)
            if checkpoint_id:
                attrs[SDK_HITL_CHECKPOINT_ID] = checkpoint_id
            _record_hitl(**attrs)

    return _HITLLifecycleHandler