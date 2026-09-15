"""Shared SDK <-> backend contract.

Single source of truth for:
- attribute names the SDK emits and the backend consumes (``sdk.*`` namespaced,
  OpenInference names, ``exception.*``),
- the authoritative failure taxonomy (``ERROR_KINDS``) and span kinds,
- payload-redaction rules,
- best-effort classification hint patterns.

The SDK emits exactly these names; the backend reads exactly these names. Keep
them in lockstep by importing from here rather than re-declaring.
"""
from __future__ import annotations

import re

# --- SDK namespaced attributes ------------------------------------------------
SDK_CLIENT_ID = "sdk.client_id"
SDK_PROJECT_ID = "sdk.project_id"
SDK_WORKFLOW_ID = "sdk.workflow_id"
SDK_WORKFLOW_VERSION = "sdk.workflow.version"
SDK_CAPTURE_PROMPTS = "sdk.capture_prompts"
SDK_ERROR_TYPE = "sdk.error.type"
SDK_ERROR_MESSAGE = "sdk.error.message"
SDK_ERROR_KIND = "sdk.error.kind"
SDK_RETRY_OF = "sdk.retry.of"
SDK_RETRY_COUNT = "sdk.retry.count"
SDK_TOKENS_ESTIMATED = "sdk.tokens.estimated"
SDK_HITL_THREAD_ID = "sdk.hitl.thread_id"
SDK_HITL_INTERRUPTED = "sdk.hitl.interrupted"
SDK_HITL_RESUMED = "sdk.hitl.resumed"
SDK_HITL_INTERRUPT_PAYLOAD = "sdk.hitl.interrupt_payload"
SDK_HITL_RESUME_VALUE = "sdk.hitl.resume_value"
SDK_HITL_NODE = "sdk.hitl.node"
SDK_HITL_CHECKPOINT_ID = "sdk.hitl.checkpoint_id"

# --- OpenInference / standard attribute names ---------------------------------
OI_SPAN_KIND = "openinference.span.kind"
SESSION_ID = "session.id"
USER_ID = "user.id"
METADATA = "metadata"
INPUT_VALUE = "input.value"
INPUT_MIME_TYPE = "input.mime_type"
OUTPUT_VALUE = "output.value"
OUTPUT_MIME_TYPE = "output.mime_type"
LLM_INPUT_MESSAGES = "llm.input_messages"
LLM_OUTPUT_MESSAGES = "llm.output_messages"
LLM_PROMPTS = "llm.prompts"
LLM_CHOICES = "llm.choices"
LLM_MODEL_NAME = "llm.model_name"
LLM_PROVIDER = "llm.provider"
LLM_SYSTEM = "llm.system"
LLM_INVOCATION_PARAMETERS = "llm.invocation_parameters"
LLM_TOKEN_COUNT_PROMPT = "llm.token_count.prompt"
LLM_TOKEN_COUNT_COMPLETION = "llm.token_count.completion"
LLM_TOKEN_COUNT_TOTAL = "llm.token_count.total"
LLM_TOKEN_COUNT_PROMPT_CACHE_READ = "llm.token_count.prompt_details.cache_read"
LLM_TOKEN_COUNT_PROMPT_CACHE_WRITE = "llm.token_count.prompt_details.cache_write"
LLM_TOKEN_COUNT_COMPLETION_REASONING = "llm.token_count.completion_details.reasoning"
TOOL_NAME = "tool.name"
TOOL_PARAMETERS = "tool.parameters"
DOCUMENT_CONTENT = "document.content"
RETRIEVAL_DOCUMENTS = "retrieval.documents"
RERANKER_INPUT_DOCUMENTS = "reranker.input.documents"
RERANKER_OUTPUT_DOCUMENTS = "reranker.output.documents"

# Message payload attributes
MESSAGE_CONTENT = "message.content"
MESSAGE_ROLE = "message.role"

# --- Exception event names ----------------------------------------------------
EXCEPTION_TYPE = "exception.type"
EXCEPTION_MESSAGE = "exception.message"
EXCEPTION_STACKTRACE = "exception.stacktrace"
EXCEPTION_EVENT_NAME = "exception"

# --- OpenInference span kinds -------------------------------------------------
KIND_LLM = "LLM"
KIND_CHAIN = "CHAIN"
KIND_AGENT = "AGENT"
KIND_TOOL = "TOOL"
KIND_RETRIEVER = "RETRIEVER"
KIND_EMBEDDING = "EMBEDDING"
KIND_RERANKER = "RERANKER"
KIND_GUARDRAIL = "GUARDRAIL"
KIND_EVALUATOR = "EVALUATOR"
KIND_PROMPT = "PROMPT"
KIND_UNKNOWN = "UNKNOWN"

# --- Authoritative failure taxonomy (backend owns it; SDK hints subset) -------
KIND_RATE_LIMIT = "rate_limit"
KIND_TIMEOUT = "timeout"
KIND_INVALID_OUTPUT = "invalid_output"
KIND_TOOL_ERROR = "tool_error"
KIND_PROVIDER_ERROR = "provider_error"
KIND_RETRIEVAL_ERROR = "retrieval_error"
KIND_VALIDATION_ERROR = "validation_error"
KIND_BUSINESS_LOGIC = "business_logic"

ERROR_KINDS = frozenset(
    {
        KIND_RATE_LIMIT,
        KIND_TIMEOUT,
        KIND_INVALID_OUTPUT,
        KIND_TOOL_ERROR,
        KIND_PROVIDER_ERROR,
        KIND_RETRIEVAL_ERROR,
        KIND_VALIDATION_ERROR,
        KIND_BUSINESS_LOGIC,
    }
)

# Hints the SDK may stamp; backend may refine/override (authoritative).
SDK_HINTS = frozenset(
    {KIND_RATE_LIMIT, KIND_TIMEOUT, KIND_INVALID_OUTPUT, KIND_TOOL_ERROR, KIND_PROVIDER_ERROR}
)

# Generic layer fallback when a raw ERROR has no recognizable text.
LAYER_ERROR_KIND = {
    KIND_LLM: KIND_PROVIDER_ERROR,
    KIND_TOOL: KIND_TOOL_ERROR,
    KIND_RETRIEVER: KIND_RETRIEVAL_ERROR,
}

# --- Payload redaction --------------------------------------------------------
PAYLOAD_STRIP_EXACT = frozenset(
    {
        INPUT_VALUE,
        INPUT_MIME_TYPE,
        OUTPUT_VALUE,
        OUTPUT_MIME_TYPE,
        TOOL_PARAMETERS,
        DOCUMENT_CONTENT,
    }
)

PAYLOAD_STRIP_PREFIXES = (
    f"{LLM_INPUT_MESSAGES}.",
    f"{LLM_OUTPUT_MESSAGES}.",
    f"{LLM_PROMPTS}.",
    f"{LLM_CHOICES}.",
    f"{RETRIEVAL_DOCUMENTS}.",
    f"{RERANKER_INPUT_DOCUMENTS}.",
    f"{RERANKER_OUTPUT_DOCUMENTS}.",
    f"{DOCUMENT_CONTENT}.",
)


def is_payload_attribute(key: str) -> bool:
    """True when the attribute key carries prompt/response payload."""
    if key in PAYLOAD_STRIP_EXACT:
        return True
    return key.startswith(PAYLOAD_STRIP_PREFIXES)


# --- Metadata redaction (business context persisted by the backend) ----------
REDACTED = "[redacted]"

SENSITIVE_METADATA_KEY = re.compile(
    r"pass(word|wd)?|secret|token|api[_-]?key|authorization|credential|ssn|credit[_-]?card",
    re.IGNORECASE,
)


def redact_metadata(value: object) -> object:
    """Return a copy of SDK metadata with sensitive values redacted (F19).

    Applied by the backend before persisting ``metadata``; nested dicts and
    lists are handled recursively so secrets cannot hide one level down.
    """
    if isinstance(value, dict):
        return {
            key: (
                REDACTED
                if isinstance(key, str) and SENSITIVE_METADATA_KEY.search(key)
                else redact_metadata(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_metadata(item) for item in value]
    return value


# --- Best-effort classification hint patterns (SDK + backend share) ----------
_HINT_RATE_LIMIT = re.compile(r"ratelimit|rate.?limit|throttl|429")
_HINT_TIMEOUT = re.compile(r"timeout|timed.?out|deadline")
_HINT_INVALID_OUTPUT = re.compile(
    r"jsondecodeerror|outputparser|expecting value|json.?decode|parse.?error|invalid json"
)
_HINT_VALIDATION = re.compile(
    r"validation failed|validation error|pydantic|schema validation|assertion failed|assert "
)


def match_hint(text: str | None) -> str | None:
    """Return the best-effort hint kind for raw exception text, or None.

    Specific signals first, generic fallbacks last.
    """
    combined = (text or "").lower()
    if not combined:
        return None
    if _HINT_RATE_LIMIT.search(combined):
        return KIND_RATE_LIMIT
    if _HINT_TIMEOUT.search(combined):
        return KIND_TIMEOUT
    if _HINT_INVALID_OUTPUT.search(combined):
        return KIND_INVALID_OUTPUT
    if _HINT_VALIDATION.search(combined):
        return KIND_VALIDATION_ERROR
    return None