"""Estimated token usage is marked (F33)."""

from __future__ import annotations

from ai_observability._attributes import SDK_TOKENS_ESTIMATED
from ai_observability._usage import backfill_token_counts


def test_backfilled_tokens_are_marked_estimated():
    attrs = {
        "llm.input_messages.0.message.role": "user",
        "llm.input_messages.0.message.content": "hello " * 20,
        "llm.output_messages.0.message.role": "assistant",
        "llm.output_messages.0.message.content": "world " * 20,
    }
    backfill_token_counts(attrs)
    assert attrs[SDK_TOKENS_ESTIMATED] is True
    assert attrs["llm.token_count.prompt"] > 0
    assert attrs["llm.token_count.completion"] > 0
    assert (
        attrs["llm.token_count.total"]
        == attrs["llm.token_count.prompt"] + attrs["llm.token_count.completion"]
    )


def test_reported_tokens_are_not_marked():
    attrs = {"llm.token_count.prompt": 10, "llm.token_count.completion": 5}
    backfill_token_counts(attrs)
    assert SDK_TOKENS_ESTIMATED not in attrs


def test_total_only_backfill_is_not_marked_estimated():
    attrs = {
        "llm.token_count.prompt": 10,
        "llm.token_count.completion": 5,
        "llm.token_count.total": 1,
    }
    backfill_token_counts(attrs)
    assert attrs["llm.token_count.total"] == 15
    assert SDK_TOKENS_ESTIMATED not in attrs
