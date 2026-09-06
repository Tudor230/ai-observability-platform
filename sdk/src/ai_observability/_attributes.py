"""Namespaced SDK attribute names and OpenInference attribute key helpers.

The SDK emits OpenInference semantic conventions for everything with a
convention, plus its own ``sdk.*`` namespaced attributes for material that has
no convention (failure material, retries, business context, capture flags).
The backend consumes ``sdk.*`` attributes; Phoenix stores them as-is.
"""

from openinference.semconv.trace import (
    DocumentAttributes,
    MessageAttributes,
    RerankerAttributes,
    SpanAttributes,
)

# --- SDK namespaced attributes -------------------------------------------------

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

# --- OpenInference attribute names we rely on ---------------------------------

OPENINFERENCE_SPAN_KIND = SpanAttributes.OPENINFERENCE_SPAN_KIND
SESSION_ID = SpanAttributes.SESSION_ID
USER_ID = SpanAttributes.USER_ID
METADATA = SpanAttributes.METADATA
INPUT_VALUE = SpanAttributes.INPUT_VALUE
INPUT_MIME_TYPE = SpanAttributes.INPUT_MIME_TYPE
OUTPUT_VALUE = SpanAttributes.OUTPUT_VALUE
OUTPUT_MIME_TYPE = SpanAttributes.OUTPUT_MIME_TYPE
LLM_INPUT_MESSAGES = SpanAttributes.LLM_INPUT_MESSAGES
LLM_OUTPUT_MESSAGES = SpanAttributes.LLM_OUTPUT_MESSAGES
LLM_MODEL_NAME = SpanAttributes.LLM_MODEL_NAME
LLM_PROVIDER = SpanAttributes.LLM_PROVIDER
LLM_SYSTEM = SpanAttributes.LLM_SYSTEM
LLM_INVOCATION_PARAMETERS = SpanAttributes.LLM_INVOCATION_PARAMETERS
LLM_TOKEN_COUNT_PROMPT = SpanAttributes.LLM_TOKEN_COUNT_PROMPT
LLM_TOKEN_COUNT_COMPLETION = SpanAttributes.LLM_TOKEN_COUNT_COMPLETION
LLM_TOKEN_COUNT_TOTAL = SpanAttributes.LLM_TOKEN_COUNT_TOTAL
TOOL_NAME = SpanAttributes.TOOL_NAME
TOOL_PARAMETERS = SpanAttributes.TOOL_PARAMETERS

MESSAGE_CONTENT = MessageAttributes.MESSAGE_CONTENT
MESSAGE_ROLE = MessageAttributes.MESSAGE_ROLE

EXCEPTION_TYPE = "exception.type"
EXCEPTION_MESSAGE = "exception.message"
EXCEPTION_STACKTRACE = "exception.stacktrace"
EXCEPTION_EVENT_NAME = "exception"

# Span-kind values the SDK itself creates.
CHAIN_KIND = "CHAIN"

# --- Payload attribute redaction ----------------------------------------------

_DOCUMENT_CONTENT = DocumentAttributes.DOCUMENT_CONTENT

# Exact attribute keys stripped when prompt/response capture is off.
_PAYLOAD_STRIP_EXACT = frozenset(
    {
        INPUT_VALUE,
        INPUT_MIME_TYPE,
        OUTPUT_VALUE,
        OUTPUT_MIME_TYPE,
        TOOL_PARAMETERS,
        _DOCUMENT_CONTENT,
    }
)

# Attribute key prefixes stripped when prompt/response capture is off.
_PAYLOAD_STRIP_PREFIXES = (
    f"{SpanAttributes.LLM_INPUT_MESSAGES}.",
    f"{SpanAttributes.LLM_OUTPUT_MESSAGES}.",
    f"{SpanAttributes.LLM_PROMPTS}.",
    f"{SpanAttributes.LLM_CHOICES}.",
    f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.",
    f"{RerankerAttributes.RERANKER_INPUT_DOCUMENTS}.",
    f"{RerankerAttributes.RERANKER_OUTPUT_DOCUMENTS}.",
    f"{_DOCUMENT_CONTENT}.",
)


def is_payload_attribute(key: str) -> bool:
    """Return True when the attribute key carries prompt/response payload."""
    if key in _PAYLOAD_STRIP_EXACT:
        return True
    return key.startswith(_PAYLOAD_STRIP_PREFIXES)