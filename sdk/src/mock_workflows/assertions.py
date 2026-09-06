"""Programmatic trace assertions for mock-workflow scenarios.

No golden files: every assertion derives from the exported (enriched) OTLP
spans — trace shape, attributes, token counts, failure propagation.
"""

from __future__ import annotations

import json
from typing import Optional

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace.status import StatusCode

from ai_observability._attributes import (
    EXCEPTION_EVENT_NAME,
    OPENINFERENCE_SPAN_KIND,
)

_STATUS_ERROR = StatusCode.ERROR
_STATUS_OK = StatusCode.OK


class ScenarioAssertions:
    def __init__(self, spans: list[ReadableSpan]) -> None:
        self.spans_all = spans
        self.failures: list[str] = []

    # -- discovery ------------------------------------------------------------

    def root(self) -> Optional[ReadableSpan]:
        for span in self.spans_all:
            parent = span.parent
            if parent is None or parent.is_remote:
                return span
        return None

    def spans(self, *, kind: Optional[str] = None, name: Optional[str] = None) -> list[ReadableSpan]:
        result = []
        for span in self.spans_all:
            if kind is not None and self.kind_of(span) != kind:
                continue
            if name is not None and span.name != name:
                continue
            result.append(span)
        return result

    def kind_of(self, span: ReadableSpan) -> Optional[str]:
        value = (span.attributes or {}).get(OPENINFERENCE_SPAN_KIND)
        return value if isinstance(value, str) else None

    def attrs(self, span: ReadableSpan) -> dict:
        return dict(span.attributes or {})

    # -- assertions -----------------------------------------------------------

    def require(self, condition: bool, message: str) -> None:
        if not condition:
            self.failures.append(message)

    def require_single_root(self, name: str) -> Optional[ReadableSpan]:
        roots = self.spans_all if not self.spans_all else [
            s for s in self.spans_all if s.parent is None or s.parent.is_remote
        ]
        self.require(len(roots) == 1, f"expected exactly 1 trace root, got {len(roots)}")
        if len(roots) != 1:
            return None
        self.require(roots[0].name == name, f"root name {roots[0].name!r} != {name!r}")
        self.require(self.kind_of(roots[0]) == "CHAIN", "root span kind must be CHAIN")
        return roots[0]

    def require_span(self, *, kind: str, name: Optional[str] = None) -> Optional[ReadableSpan]:
        found = self.spans(kind=kind, name=name)
        self.require(len(found) >= 1, f"expected a {kind} span" + (f" named {name!r}" if name else ""))
        return found[0] if found else None

    def parent_is(self, span: ReadableSpan, parent: ReadableSpan) -> None:
        if span.parent is None or parent.context is None:
            self.require(
                span.parent == parent.context,
                f"{span.name!r} has no parent; expected {parent.name!r}",
            )
            return
        self.require(
            span.parent.span_id == parent.context.span_id,
            f"{span.name!r} parent != {parent.name!r}",
        )

    def descendant_of(self, span: ReadableSpan, ancestor: ReadableSpan) -> None:
        """Require ``span`` to be a (not necessarily direct) descendant."""
        if ancestor.context is None or span.parent is None:
            self.require(
                span.parent == ancestor.context,
                f"{span.name!r} is not a descendant of {ancestor.name!r}",
            )
            return
        by_id = {s.context.span_id: s for s in self.spans_all if s.context is not None}
        current: Optional[ReadableSpan] = span
        while current is not None and current.context is not None:
            if current.parent is not None and current.parent.span_id == ancestor.context.span_id:
                self.require(
                    True, f"{span.name!r} is not a descendant of {ancestor.name!r}"
                )
                return
            current = by_id.get(current.parent.span_id) if current.parent is not None else None
        self.require(
            False, f"{span.name!r} is not a descendant of {ancestor.name!r}"
        )

    def attr_eq(self, span: ReadableSpan, key: str, expected) -> None:
        value = self.attrs(span).get(key)
        self.require(value == expected, f"{span.name!r}.{key} = {value!r}, expected {expected!r}")

    def attr_is_int(self, span: ReadableSpan, key: str) -> None:
        value = self.attrs(span).get(key)
        self.require(
            isinstance(value, int) and not isinstance(value, bool),
            f"{span.name!r}.{key} = {value!r}, expected an int",
        )

    def attr_is_str(self, span: ReadableSpan, key: str) -> None:
        value = self.attrs(span).get(key)
        self.require(
            isinstance(value, str),
            f"{span.name!r}.{key} = {value!r}, expected a string",
        )

    def attr_contains(self, span: ReadableSpan, key: str, substring: str) -> None:
        value = self.attrs(span).get(key)
        self.require(
            isinstance(value, str) and substring in value,
            f"{span.name!r}.{key} = {value!r}, expected to contain {substring!r}",
        )

    def status_ok(self, span: ReadableSpan) -> None:
        code = span.status.status_code if span.status else None
        self.require(code == _STATUS_OK, f"{span.name!r} status = {code}, expected OK")

    def status_error(self, span: ReadableSpan) -> None:
        code = span.status.status_code if span.status else None
        self.require(code == _STATUS_ERROR, f"{span.name!r} status = {code}, expected ERROR")

    def status_is_error(self, span: ReadableSpan) -> bool:
        return span.status is not None and span.status.status_code == _STATUS_ERROR

    def has_exception_event(self, span: ReadableSpan) -> bool:
        return any(e.name == EXCEPTION_EVENT_NAME for e in span.events)

    def metadata_json(self, span: ReadableSpan) -> Optional[dict]:
        raw = self.attrs(span).get("metadata")
        if not isinstance(raw, str):
            return None
        try:
            return json.loads(raw)
        except ValueError:
            return None