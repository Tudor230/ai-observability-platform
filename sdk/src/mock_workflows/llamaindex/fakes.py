"""LlamaIndex mock fixtures: scripted fake LLM, fixed retriever, tools.

``ScriptedMockLLM`` subclasses ``MockLLM`` and overrides ``complete`` with the
``llm_completion_callback`` decorator so the OpenInference callback system
sees a full LLM event carrying ``raw`` usage (deterministic token counts).
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from llama_index.core.llms import CompletionResponse, MockLLM
from llama_index.core.llms.callbacks import llm_completion_callback
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, TextNode


class MockRateLimitError(Exception):
    """Name signals rate limiting to the SDK's classification hints."""


class ScriptedMockLLM(MockLLM):
    """Cycles fixed responses with fixed usage; optional sleep and fail budget."""

    def __init__(
        self,
        responses: list[str],
        prompt_tokens: int,
        completion_tokens: int,
        *,
        sleep: float = 0.0,
        fail_budget: int = 0,
        fail_exception: Optional[Callable[[], Exception]] = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._responses = list(responses)
        self._usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }
        self._sleep = sleep
        self._fail_budget = fail_budget
        self._fail_exception = fail_exception
        self._i = 0

    @llm_completion_callback()
    def complete(self, prompt: str, formatted: bool = False, **kwargs) -> CompletionResponse:
        if self._sleep:
            time.sleep(self._sleep)
        if self._fail_budget > 0:
            self._fail_budget -= 1
            if self._fail_exception is not None:
                raise self._fail_exception()
            raise RuntimeError("scripted failure")
        response = self._responses[self._i % len(self._responses)]
        self._i += 1
        return CompletionResponse(
            text=response,
            raw={
                "usage": self._usage,
                "choices": [{"message": {"role": "assistant", "content": response}}],
            },
        )


class FixedRetriever(BaseRetriever):
    """Retrieves a fixed document (deterministic)."""

    document_text: str = "order 123 is shipped"
    document_id: str = "doc-1"

    def _retrieve(self, query_bundle):
        node = TextNode(text=self.document_text, id_=self.document_id)
        return [NodeWithScore(node=node, score=0.95)]


class FailingRetriever(BaseRetriever):
    """Always fails (deterministic retrieval failure)."""

    def _retrieve(self, query_bundle):
        raise RuntimeError("vector store unavailable")