"""Retry inference: sdk.retry.count / sdk.retry.of.

Mechanism (research ticket 09): no framework surfaces actual attempt counts.
The SDK infers them from span structure at trace end:

* LangChain ``with_retry`` re-fires child attempts under the retried run
  (one child run per attempt, failed attempts = ERROR spans). When a
  non-error LLM/TOOL span has same-kind, same-name failed children, the
  failed children are retried attempts.
* Framework/agent-level retry loops show up as repeated sibling ERROR spans
  next to the successful one. When a successful LLM/TOOL span has same-parent,
  same-kind, same-name failed siblings, they are retried attempts.

``sdk.retry.of`` is read from ``llm.invocation_parameters.max_retries`` where
the framework exposes it (LangChain+Anthropic today).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace.status import StatusCode

from ._attributes import (
    OPENINFERENCE_SPAN_KIND,
    SDK_RETRY_COUNT,
    SDK_RETRY_OF,
)
from ._usage import retry_budget

_RETRYABLE_KINDS = frozenset({"LLM", "TOOL"})


def _is_error(span: ReadableSpan) -> bool:
    return span.status is not None and span.status.status_code == StatusCode.ERROR


def _is_success(span: ReadableSpan) -> bool:
    return not _is_error(span)


def _oi_kind(span: ReadableSpan) -> Optional[str]:
    value = (span.attributes or {}).get(OPENINFERENCE_SPAN_KIND)
    return value if isinstance(value, str) else None


def infer_retries(spans: list[ReadableSpan]) -> dict[int, int]:
    """Return {span_id: retry_count} for spans with inferred retries.

    ``spans`` is the complete list of spans in one trace (already parented).
    """
    counts: dict[int, int] = {}
    by_parent: dict[int, list[ReadableSpan]] = defaultdict(list)
    for span in spans:
        parent = span.parent
        if parent is not None:
            by_parent[parent.span_id].append(span)

    # Child-attempt rule: retried run with failed attempt children.
    for parent_span in spans:
        if _oi_kind(parent_span) not in _RETRYABLE_KINDS:
            continue
        if parent_span.context is None:
            continue
        children = by_parent.get(parent_span.context.span_id, [])
        same = [
            c
            for c in children
            if _oi_kind(c) in _RETRYABLE_KINDS and c.name == parent_span.name
        ]
        failed = [c for c in same if _is_error(c)]
        ok = [c for c in same if _is_success(c)]
        if ok and failed:
            counts[parent_span.context.span_id] = len(failed)

    # Sibling-attempt rule: successful span preceded by failed siblings.
    for span in spans:
        if _oi_kind(span) not in _RETRYABLE_KINDS or not _is_success(span):
            continue
        if span.context is None:
            continue
        if span.context.span_id in counts:
            continue
        parent = span.parent
        if parent is None:
            continue
        siblings = by_parent.get(parent.span_id, [])
        failed = [
            s
            for s in siblings
            if s is not span
            and _oi_kind(s) in _RETRYABLE_KINDS
            and _is_error(s)
            and s.name == span.name
        ]
        if failed:
            counts[span.context.span_id] = len(failed)

    return counts


def enrich_retry_attributes(
    span: ReadableSpan, attributes: dict, retry_count: Optional[int]
) -> dict:
    if retry_count is not None and SDK_RETRY_COUNT not in attributes:
        attributes[SDK_RETRY_COUNT] = retry_count
    if SDK_RETRY_OF not in attributes:
        budget = retry_budget(attributes)
        if budget is not None:
            attributes[SDK_RETRY_OF] = budget
    return attributes