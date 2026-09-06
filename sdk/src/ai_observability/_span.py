"""Manual span helper for business steps outside framework coverage."""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterator, Optional

from opentelemetry.trace import Span, SpanKind, Status, StatusCode

from ._attributes import CHAIN_KIND, METADATA, OPENINFERENCE_SPAN_KIND
from ._state import get_state


@contextmanager
def span(name: str, context: Optional[dict] = None) -> Iterator[Span]:
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