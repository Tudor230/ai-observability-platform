"""Usage capture: provider normalization and token-count validation/backfill.

The SDK never emits ``llm.cost.*`` — Phoenix computes cost server-side from
token counts + model pricing. The SDK only guarantees accurate
``llm.model_name``/``llm.provider`` and complete ``llm.token_count.*``.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from typing import Optional

from ._attributes import (
    LLM_INPUT_MESSAGES,
    LLM_MODEL_NAME,
    LLM_OUTPUT_MESSAGES,
    LLM_PROVIDER,
    LLM_SYSTEM,
    LLM_TOKEN_COUNT_COMPLETION,
    LLM_TOKEN_COUNT_PROMPT,
    LLM_TOKEN_COUNT_TOTAL,
    MESSAGE_CONTENT,
    MESSAGE_ROLE,
)

logger = logging.getLogger(__name__)

_NA = "_NA"

# Model-name prefix -> OpenInference provider value. Covers providers the
# LangChain instrumentor's map leaves unset or maps to _NA (deepseek, xai,
# perplexity, fireworks, huggingface, ...). Ambiguous prefixes (e.g. bare
# "llama") are intentionally absent — we do not guess.
_MODEL_PREFIX_TO_PROVIDER = (
    ("accounts/fireworks", "fireworks"),
    ("firefunction", "fireworks"),
    ("deepseek", "deepseek"),
    ("grok-", "xai"),
    ("sonar", "perplexity"),
    ("pplx-", "perplexity"),
    ("huggingface", "huggingface"),
    ("hf-", "huggingface"),
    ("moonshot", "moonshot"),
    ("kimi", "moonshot"),
    ("cerebras", "cerebras"),
    ("gpt-", "openai"),
    ("chatgpt-", "openai"),
    ("o1-", "openai"),
    ("o3-", "openai"),
    ("o4-", "openai"),
    ("claude", "anthropic"),
    ("gemini", "google"),
    ("command-", "cohere"),
    ("c4ai-", "cohere"),
    ("mistral", "mistralai"),
    ("mixtral", "mistralai"),
    ("pixtral", "mistralai"),
    ("open-mistral", "mistralai"),
)

# llm.system fallback: system name -> provider name (only unambiguous ones).
_SYSTEM_TO_PROVIDER = {
    "openai": "openai",
    "anthropic": "anthropic",
    "cohere": "cohere",
    "mistralai": "mistralai",
    "vertexai": "google",
}

_BACKFILL_TIKTOKEN_ENV = "AI_OBSERVABILITY_BACKFILL_TIKTOKEN"


def normalize_provider(attributes: dict) -> None:
    """Fill ``llm.provider`` when missing or ``_NA``, in place."""
    current = attributes.get(LLM_PROVIDER)
    if isinstance(current, str) and current and current != _NA:
        return
    provider = _infer_provider(attributes)
    if provider is not None:
        attributes[LLM_PROVIDER] = provider


def _infer_provider(attributes: dict) -> Optional[str]:
    model_name = attributes.get(LLM_MODEL_NAME)
    if isinstance(model_name, str) and model_name:
        lowered = model_name.lower()
        for prefix, provider in _MODEL_PREFIX_TO_PROVIDER:
            if lowered.startswith(prefix):
                return provider
    system = attributes.get(LLM_SYSTEM)
    if isinstance(system, str) and system:
        return _SYSTEM_TO_PROVIDER.get(system.lower())
    return None


def backfill_token_counts(attributes: dict) -> None:
    """Validate and backfill ``llm.token_count.prompt/completion/total``.

    * Missing counts are estimated from captured messages (tiktoken when
      enabled and the model is known, otherwise a deterministic character
      estimate).
    * ``total`` is recomputed as prompt + completion when missing or wrong.
    Runs before payload redaction so hidden messages still backfill counts.
    """
    prompt = _as_int(attributes.get(LLM_TOKEN_COUNT_PROMPT))
    completion = _as_int(attributes.get(LLM_TOKEN_COUNT_COMPLETION))
    if prompt is None:
        prompt = _estimate_prompt_tokens(attributes)
    if completion is None:
        completion = _estimate_completion_tokens(attributes)
    if prompt is not None:
        attributes[LLM_TOKEN_COUNT_PROMPT] = prompt
    if completion is not None:
        attributes[LLM_TOKEN_COUNT_COMPLETION] = completion
    if prompt is not None and completion is not None:
        total = _as_int(attributes.get(LLM_TOKEN_COUNT_TOTAL))
        if total is None or total != prompt + completion:
            attributes[LLM_TOKEN_COUNT_TOTAL] = prompt + completion
    elif (total := _as_int(attributes.get(LLM_TOKEN_COUNT_TOTAL))) is not None:
        attributes[LLM_TOKEN_COUNT_TOTAL] = total


def _as_int(value) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _estimate_prompt_tokens(attributes: dict) -> Optional[int]:
    texts = _input_message_texts(attributes)
    if not texts:
        return None
    model = attributes.get(LLM_MODEL_NAME)
    return _estimate_tokens("\n".join(texts), model)


def _estimate_completion_tokens(attributes: dict) -> Optional[int]:
    texts = _output_message_texts(attributes)
    if not texts:
        return None
    model = attributes.get(LLM_MODEL_NAME)
    return _estimate_tokens("\n".join(texts), model)


def _input_message_texts(attributes: dict) -> list[str]:
    return _collect_message_texts(attributes, LLM_INPUT_MESSAGES)


def _output_message_texts(attributes: dict) -> list[str]:
    return _collect_message_texts(attributes, LLM_OUTPUT_MESSAGES)


def _collect_message_texts(attributes: dict, prefix: str) -> list[str]:
    texts: list[str] = []
    index = 0
    while True:
        role = attributes.get(f"{prefix}.{index}.{MESSAGE_ROLE}")
        content = attributes.get(f"{prefix}.{index}.{MESSAGE_CONTENT}")
        if role is None and content is None:
            break
        if isinstance(content, str) and content:
            texts.append(content)
        index += 1
    return texts


def _estimate_tokens(text: str, model_name=None) -> int:
    if text is None or not text:
        return 0
    encoding = _tiktoken_encoding(model_name)
    if encoding is not None:
        try:
            return len(encoding.encode(text))
        except Exception:
            logger.debug("tiktoken encode failed, falling back to estimate", exc_info=True)
    return max(1, math.ceil(len(text) / 4))


_encoding_cache = {}


def _tiktoken_encoding(model_name=None):
    if os.environ.get(_BACKFILL_TIKTOKEN_ENV, "").strip().lower() not in ("1", "true", "yes"):
        return None
    if model_name in _encoding_cache:
        return _encoding_cache[model_name]
    try:
        import tiktoken  # optional dependency
    except ImportError:
        return None
    encoding_name = _model_to_encoding(model_name)
    if encoding_name is None:
        return None
    try:
        encoding = tiktoken.get_encoding(encoding_name)
        _encoding_cache[model_name] = encoding
        return encoding
    except Exception:
        logger.debug("tiktoken unavailable for %r", model_name, exc_info=True)
        return None


def _model_to_encoding(model_name) -> Optional[str]:
    if not model_name:
        return None
    lowered = model_name.lower()
    if "gpt-4" in lowered or "gpt-3.5" in lowered or "gpt-35" in lowered:
        return "cl100k_base"
    if "gpt-" in lowered or lowered.startswith("o1") or lowered.startswith("o3") or lowered.startswith("o4"):
        return "o200k_base"
    return None


def retry_budget(attributes: dict) -> Optional[int]:
    """Read ``max_retries`` from ``llm.invocation_parameters`` (best effort).

    Reliable today for LangChain+Anthropic; unset everywhere else (the
    LangChain+OpenAI and LlamaIndex instrumentor paths do not emit it).
    """
    raw = attributes.get("llm.invocation_parameters")
    if not isinstance(raw, str):
        return None
    try:
        params = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(params, dict):
        return None
    value = params.get("max_retries")
    return value if isinstance(value, int) and value >= 0 else None