"""Groq mock fixtures: scripted chat completions at the HTTP boundary.

The real ``groq`` client and the real OpenInference instrumentor run; only the
HTTP transport is replaced with ``httpx.MockTransport`` (injected through the
client's ``http_client`` argument), so scenarios need no API key and no
network. Mirrors the fake-model approach of the Ollama suite: deterministic
content, fixed token counts and scripted failures.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx

MODEL = "openai/gpt-oss-120b"


def chat_completion(
    content: str,
    *,
    prompt_tokens: int = 5,
    completion_tokens: int = 4,
    model: str = MODEL,
) -> httpx.Response:
    """One successful chat completion with fixed usage."""
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-mock",
            "object": "chat.completion",
            "created": 1,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "logprobs": None,
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            "system_fingerprint": "fp_mock",
        },
    )


def rate_limit_response(message: str = "Rate limit reached for requests") -> httpx.Response:
    """A 429 that the groq client turns into ``groq.RateLimitError``."""
    return httpx.Response(
        429,
        json={
            "error": {
                "message": message,
                "type": "rate_limit_error",
                "code": "rate_limit_exceeded",
            }
        },
    )


@contextmanager
def patched_groq(*replies: Any) -> Iterator[httpx.Client]:
    """Route the Groq HTTP transport to scripted replies (no network).

    Each request consumes one reply in order: an ``httpx.Response`` is returned
    as-is, an ``Exception`` instance is raised instead. Pass the yielded
    ``httpx.Client`` to ``Groq(..., http_client=...)`` and use
    ``max_retries=0`` so a scripted failure surfaces after exactly one reply.
    """
    queue = list(replies)

    def handler(request: httpx.Request) -> httpx.Response:
        if not queue:
            raise AssertionError("patched_groq: no scripted reply left")
        reply = queue.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply

    yield httpx.Client(transport=httpx.MockTransport(handler), timeout=5)
