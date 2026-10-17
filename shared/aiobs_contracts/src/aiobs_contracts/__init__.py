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
from dataclasses import dataclass
from typing import Optional, Sequence

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

# Loop detection (ADR-0014): the SDK measures call repetition live, the
# backend re-derives it from stored spans and owns the execution-level flag.
# ``sdk.call.sig`` is a salted, run-scoped signature of a call's input — an
# opaque equality token, never the payload itself (see ADR-0003 amendment).
SDK_CALL_SIG = "sdk.call.sig"
SDK_LOOP_SIGNAL = "sdk.loop.signal"
SDK_LOOP_REPEAT_COUNT = "sdk.loop.repeat_count"
SDK_LOOP_TOOL_REPEATS = "sdk.loop.tool_repeats"
SDK_LOOP_LLM_REPEATS = "sdk.loop.llm_repeats"
SDK_LOOP_CYCLE_REPEATS = "sdk.loop.cycle_repeats"

LOOP_SIGNAL_TOOL = "tool_repeat"
LOOP_SIGNAL_LLM = "llm_repeat"
LOOP_SIGNAL_CYCLE = "cycle"

# Every signal the backend can flag on an execution.
LOOP_SIGNALS = frozenset({LOOP_SIGNAL_TOOL, LOOP_SIGNAL_LLM, LOOP_SIGNAL_CYCLE})

# Default live-measurement constants (the SDK's span/root marks). The
# authoritative thresholds are backend config; these mirror their defaults so
# a trace looks the same in Phoenix and on the platform.
LOOP_DEFAULT_THRESHOLD = 3
LOOP_CYCLE_MAX_STEPS = 4

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

# --- Control-flow exceptions (not failures) -----------------------------------
# LangGraph/LangChain exceptions that pause/resume agent execution (interrupts,
# graph-level Commands). They are expected behavior, not failures: an
# interrupted-for-approval workflow is paused, not broken. Matched as substrings
# because instrumentors report fully qualified names
# (e.g. ``langgraph.errors.GraphInterrupt``).
CONTROL_FLOW_EXCEPTION_TYPES = frozenset(
    {
        "GraphInterrupt",
        "GraphBubbleUp",
        "Command",
        "ParentCommand",
    }
)


def is_control_flow_exception(exc_type: str | None) -> bool:
    """True when an exception type names control flow rather than a failure."""
    if not exc_type:
        return False
    return any(name in exc_type for name in CONTROL_FLOW_EXCEPTION_TYPES)


# --- Loop detection: shared repeat/cycle scan (ADR-0014) ----------------------
@dataclass(frozen=True)
class LoopStep:
    """One call in an ordered sequence: kind, display name, signature."""

    kind: str
    name: str
    sig: Optional[str] = None


@dataclass(frozen=True)
class LoopScan:
    """Repeat counts over an ordered call sequence (one execution)."""

    tool_repeats: int = 0
    llm_repeats: int = 0
    cycle_repeats: int = 0
    cycle_steps: tuple[str, ...] = ()

    @property
    def detected(self) -> bool:
        return bool(self.tool_repeats or self.llm_repeats or self.cycle_repeats)

    def signals(self, threshold: int = LOOP_DEFAULT_THRESHOLD) -> list[str]:
        """Signal names whose counts reached ``threshold``, in stable order."""
        found = []
        if self.tool_repeats >= threshold:
            found.append(LOOP_SIGNAL_TOOL)
        if self.llm_repeats >= threshold:
            found.append(LOOP_SIGNAL_LLM)
        if self.cycle_repeats >= threshold:
            found.append(LOOP_SIGNAL_CYCLE)
        return found


def scan_loop_steps(
    steps: Sequence[LoopStep],
    max_pattern: int = LOOP_CYCLE_MAX_STEPS,
) -> LoopScan:
    """Count identical calls and signature-equal cycles in an ordered sequence.

    Shared by the SDK (live measurement, bounded window) and the backend
    (re-derivation from stored spans) so both sides always agree.

    * ``tool_repeats`` / ``llm_repeats``: the highest number of times one
      signature repeats across the sequence, per kind.
    * ``cycle_repeats``: the highest number of *consecutive* repetitions of a
      pattern of ``2..max_pattern`` steps in which every position carries the
      same kind, name and signature. Calls without a signature break cycles —
      unknown inputs never count as equal.

    Counts are raw; callers compare them against their own threshold.
    """
    tool_counts: dict[str, int] = {}
    llm_counts: dict[str, int] = {}
    for step in steps:
        if step.sig is None:
            continue
        if step.kind == KIND_TOOL:
            tool_counts[step.sig] = tool_counts.get(step.sig, 0) + 1
        elif step.kind == KIND_LLM:
            llm_counts[step.sig] = llm_counts.get(step.sig, 0) + 1

    best_repeats = 0
    best_names: tuple[str, ...] = ()
    for length in range(2, max_pattern + 1):
        index = 0
        while index + length <= len(steps):
            block = steps[index : index + length]
            if not all(step.sig for step in block):
                index += 1
                continue
            repeats = 1
            cursor = index + length
            while (
                cursor + length <= len(steps)
                and steps[cursor : cursor + length] == block
                and all(step.sig for step in steps[cursor : cursor + length])
            ):
                repeats += 1
                cursor += length
            if repeats >= 2 and repeats > best_repeats:
                best_repeats = repeats
                best_names = tuple(step.name for step in block)
            index = cursor if repeats > 1 else index + 1

    return LoopScan(
        tool_repeats=max(tool_counts.values(), default=0),
        llm_repeats=max(llm_counts.values(), default=0),
        cycle_repeats=best_repeats,
        cycle_steps=best_names,
    )


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