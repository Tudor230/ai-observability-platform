"""Manual span helper for business steps outside framework coverage.

``span(name, context=...)`` returns a ``Span`` that works both as a context
manager and as a decorator (sync and async), with identical parameters:

    with span("validate", context={"checks": 3}):
        run_validation()

    @span(name="validate", context={"checks": 3})
    def run_validation():
        return result

The decorator form automatically captures the function's ``input.value``
(its arguments as a name -> value mapping) and ``output.value`` (return) on
the span. Exceptions propagate unchanged: the SDK tracer records the exception
event, marks the span ERROR, and the enrichment layer stamps ``sdk.error.*`` /
propagates the failure to the workflow root. Input/output visibility follows
the ``capture_prompts`` policy — they are stripped at export unless capture is
enabled.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import json
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Optional

from opentelemetry.trace import Span, SpanKind, Status, StatusCode

from ._attributes import (
    CHAIN_KIND,
    INPUT_VALUE,
    METADATA,
    OPENINFERENCE_SPAN_KIND,
    OUTPUT_VALUE,
)
from ._state import get_state


@contextmanager
def _span_cm(name: str, context: Optional[dict]) -> Iterator[Span]:
    """Emit a CHAIN span under the active workflow (name + optional context).

    Outside a workflow the span still records (best effort); exceptions are
    recorded and marked ERROR by the SDK tracer, never raised.
    """
    tracer = get_state().get_tracer()
    with tracer.start_as_current_span(name, kind=SpanKind.INTERNAL) as otel_span:
        attributes = {OPENINFERENCE_SPAN_KIND: CHAIN_KIND}
        if context is not None:
            attributes[METADATA] = json.dumps(context, default=str)
        otel_span.set_attributes(attributes)
        try:
            yield otel_span
        except BaseException:
            raise
        else:
            otel_span.set_status(Status(StatusCode.OK))


def _serialize(value: Any) -> str:
    try:
        return json.dumps(value, default=str)
    except Exception:
        return str(value)


def _call_arguments(fn: Callable, args: tuple, kwargs: dict) -> str:
    """Serialize a call's arguments as a name -> value mapping."""
    try:
        bound = inspect.signature(fn).bind(*args, **kwargs)
        bound.apply_defaults()
        return _serialize(dict(bound.arguments))
    except (TypeError, ValueError):
        return _serialize({"args": list(args), "kwargs": dict(kwargs)})


class Span:
    """One manual span, usable as a context manager or as a decorator.

    The parameters are identical in both forms: ``name`` and optional
    ``context`` (stored as OpenInference ``metadata``).
    """

    def __init__(self, name: str, context: Optional[dict] = None) -> None:
        self._name = name
        self._context = context
        self._cm: Optional[Any] = None

    # -- context manager ----------------------------------------------------

    def __enter__(self) -> Span:
        self._cm = _span_cm(self._name, self._context)
        return self._cm.__enter__()

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._cm is None:
            return False
        return self._cm.__exit__(exc_type, exc, tb)

    # -- decorator ----------------------------------------------------------

    def __call__(self, fn: Callable):
        """Decorator usage: ``@span(name=...)`` (sync and async).

        Records ``input.value`` (the call's arguments as a name -> value
        mapping) before the call and ``output.value`` (return value) on
        success. Exceptions propagate so the tracer records them and marks
        the span ERROR.
        """
        if asyncio.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args, **kwargs):
                with _span_cm(self._name, self._context) as otel_span:
                    otel_span.set_attribute(INPUT_VALUE, _call_arguments(fn, args, kwargs))
                    result = await fn(*args, **kwargs)
                    otel_span.set_attribute(OUTPUT_VALUE, _serialize(result))
                return result

            return async_wrapper

        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            with _span_cm(self._name, self._context) as otel_span:
                otel_span.set_attribute(INPUT_VALUE, _call_arguments(fn, args, kwargs))
                result = fn(*args, **kwargs)
                otel_span.set_attribute(OUTPUT_VALUE, _serialize(result))
            return result

        return sync_wrapper


def span(name: str, context: Optional[dict] = None) -> Span:
    """Return a manual CHAIN span usable as a context manager or decorator.

    Use as a context manager or as a decorator (sync and async):

        with span(name="check", context={"checks": 3}):
            run_validation()

        @span(name="check", context={"checks": 3})
        def run_validation():
            return result
    """
    return Span(name=name, context=context)