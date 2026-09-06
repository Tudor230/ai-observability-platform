"""LangChain mock fixtures: scripted fake chat models and tools.

Deterministic by construction: fixed responses, fixed usage metadata, scripted
failures (budget-based), and fixed sleeps. Fake models subclass
``FakeMessagesListChatModel`` so responses can carry tool calls and
``usage_metadata`` (which the OpenInference instrumentor turns into
``llm.token_count.*``).
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import ConfigDict


class MockRateLimitError(Exception):
    """Name signals rate limiting to the SDK's classification hints."""


class MockTimeoutError(Exception):
    """Name signals timeout to the SDK's classification hints."""


class ScriptedChatModel(FakeMessagesListChatModel):
    """Cycles scripted responses with fixed usage; fails the first
    ``fail_budget`` calls with ``fail_exception``."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    fail_budget: int = 0
    fail_exception: Optional[Callable[[], Exception]] = None

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        if self.fail_budget > 0:
            self.fail_budget -= 1
            if self.fail_exception is not None:
                raise self.fail_exception()
            raise RuntimeError("scripted failure")
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def ai_message(content: str, prompt_tokens: int, completion_tokens: int) -> AIMessage:
    return AIMessage(
        content=content,
        usage_metadata={
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    )


def tool_calling_message(
    tool_name: str,
    tool_args: dict[str, Any],
    prompt_tokens: int,
    completion_tokens: int,
) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": tool_name,
                "args": tool_args,
                "id": "call_1",
                "type": "tool_call",
            }
        ],
        usage_metadata={
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    )