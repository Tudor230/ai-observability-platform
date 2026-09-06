"""The manual workflow boundary: context manager and decorator (sync/async).

The workflow root is an OpenInference CHAIN span carrying the SDK's
namespaced business attributes; ``session.id`` is set from ``workflow_id``;
``context`` becomes OpenInference ``metadata``. Framework spans emitted by
the instrumentors nest beneath it via OTel context propagation. Workflows
can nest.
"""

from __future__ import annotations

import asyncio
import functools
import json
import logging
from typing import Any, Callable, Optional

from opentelemetry import trace as trace_api
from opentelemetry.trace import Span, SpanKind, Status, StatusCode, use_span
from opentelemetry.util.types import AttributeValue

from ._attributes import (
    CHAIN_KIND,
    METADATA,
    OPENINFERENCE_SPAN_KIND,
    SDK_CAPTURE_PROMPTS,
    SDK_CLIENT_ID,
    SDK_PROJECT_ID,
    SDK_WORKFLOW_ID,
    SDK_WORKFLOW_VERSION,
    SESSION_ID,
    USER_ID,
)
from ._state import get_state

logger = logging.getLogger(__name__)

_TRUE = "true"
_FALSE = "false"


class Workflow:
    """Boundary for one workflow execution (span root)."""

    def __init__(
        self,
        *,
        name: str,
        client_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
        version: Optional[str] = None,
        context: Optional[dict] = None,
        user_id: Optional[str] = None,
        capture_prompts: Optional[bool] = None,
    ) -> None:
        self._name = name
        self._client_id = client_id
        self._workflow_id = workflow_id
        self._version = version
        self._context = context
        self._user_id = user_id
        self._capture_prompts = capture_prompts
        self._span: Optional[Span] = None
        self._token = None

    def __enter__(self) -> "Workflow":
        span = get_state().get_tracer().start_span(
            self._name, kind=SpanKind.INTERNAL
        )
        span.set_attributes(self._build_attributes())
        self._span = span
        self._token = use_span(
            span,
            end_on_exit=False,
            record_exception=False,
            set_status_on_exception=False,
        )
        self._token.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._span is None:
            return False
        if exc is not None:
            self._span.record_exception(exc)
            self._span.set_status(Status(StatusCode.ERROR, description=str(exc)))
        else:
            self._span.set_status(Status(StatusCode.OK))
        if self._token is not None:
            self._token.__exit__(exc_type, exc, tb)
            self._token = None
        self._span.end()
        self._span = None
        return False

    def __call__(self, fn: Callable):
        """Decorator usage: ``@workflow(name=...)``."""
        if asyncio.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args, **kwargs):
                with Workflow(
                    name=self._name,
                    client_id=self._client_id,
                    workflow_id=self._workflow_id,
                    version=self._version,
                    context=self._context,
                    user_id=self._user_id,
                    capture_prompts=self._capture_prompts,
                ):
                    return await fn(*args, **kwargs)

            return async_wrapper

        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            with Workflow(
                name=self._name,
                client_id=self._client_id,
                workflow_id=self._workflow_id,
                version=self._version,
                context=self._context,
                user_id=self._user_id,
                capture_prompts=self._capture_prompts,
            ):
                return fn(*args, **kwargs)

        return sync_wrapper

    def _build_attributes(self) -> dict[str, AttributeValue]:
        state = get_state()
        config = state.config
        attributes: dict[str, AttributeValue] = {
            OPENINFERENCE_SPAN_KIND: CHAIN_KIND,
        }
        if config is not None and config.project_id:
            attributes[SDK_PROJECT_ID] = config.project_id
        if self._client_id:
            attributes[SDK_CLIENT_ID] = self._client_id
        if self._workflow_id:
            attributes[SDK_WORKFLOW_ID] = self._workflow_id
            attributes[SESSION_ID] = self._workflow_id
        if self._version:
            attributes[SDK_WORKFLOW_VERSION] = str(self._version)
        if self._user_id:
            attributes[USER_ID] = self._user_id
        if self._context is not None:
            attributes[METADATA] = json.dumps(self._context, default=str)
        if self._capture_prompts is not None:
            attributes[SDK_CAPTURE_PROMPTS] = (
                _TRUE if self._capture_prompts else _FALSE
            )
        return attributes


def workflow(
    *,
    name: str,
    client_id: Optional[str] = None,
    workflow_id: Optional[str] = None,
    version: Optional[str] = None,
    context: Optional[dict] = None,
    user_id: Optional[str] = None,
    capture_prompts: Optional[bool] = None,
) -> Workflow:
    """Bound a workflow execution.

    Use as a context manager or as a decorator (sync and async):

        with workflow(name="checkout", client_id="client-42",
                      workflow_id="order-123", context={"channel": "web"}):
            run_agent()

        @workflow(name="checkout", client_id="client-42")
        async def run_checkout(order_id):
            ...
    """
    return Workflow(
        name=name,
        client_id=client_id,
        workflow_id=workflow_id,
        version=version,
        context=context,
        user_id=user_id,
        capture_prompts=capture_prompts,
    )