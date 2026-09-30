"""Ollama mock fixtures: scripted chat responses at the HTTP boundary.

The real ``ollama`` client and the real OpenInference instrumentor run; only
``Client._request`` (the HTTP call) is replaced, so scenarios need no local
Ollama server. Mirrors the fake-model approach of the LangChain/LlamaIndex
suites: deterministic content, fixed token counts, scripted failures, and
streamed chunks.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Sequence

from ollama._client import Client
from ollama._types import ChatResponse, Message, ResponseError

MODEL = "granite4.2:3b"


def chat_response(
    content: str,
    *,
    prompt_tokens: int = 5,
    completion_tokens: int = 4,
    model: str = MODEL,
    done: bool = True,
) -> ChatResponse:
    """A single ``ChatResponse`` with fixed usage (``prompt_eval_count``)."""
    return ChatResponse(
        model=model,
        created_at="2026-09-30T00:00:00Z",
        message=Message(role="assistant", content=content),
        done=done,
        done_reason="stop" if done else None,
        prompt_eval_count=prompt_tokens if done else None,
        eval_count=completion_tokens if done else None,
    )


def stream_chunks(
    pieces: Sequence[str],
    *,
    prompt_tokens: int = 5,
    completion_tokens: int = 4,
    model: str = MODEL,
) -> list[ChatResponse]:
    """Content fragments followed by a final chunk carrying model + usage."""
    chunks = [
        chat_response(piece, model=model, done=False) for piece in pieces
    ]
    chunks.append(
        chat_response(
            "",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model=model,
        )
    )
    return chunks


class MockRateLimitError(ResponseError):
    """429-style failure: name/message signal rate limiting to the hints."""


@contextmanager
def patched_ollama(*replies: Any) -> Iterator[None]:
    """Route ``Client._request`` to scripted replies (no HTTP, no server).

    Each reply is returned for one call, in order; an ``Exception`` instance is
    raised instead. Streaming calls receive their reply as an iterator (pass
    ``stream_chunks(...)`` for a completed stream, or an exception for a
    mid-stream failure). The original method is restored on exit.
    """
    original = Client._request
    queue = list(replies)

    def fake_request(self, cls, *args, stream: bool = False, **kwargs):
        if not queue:
            raise AssertionError("patched_ollama: no scripted reply left")
        reply = queue.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return iter(reply) if stream else reply

    Client._request = fake_request
    try:
        yield
    finally:
        Client._request = original
