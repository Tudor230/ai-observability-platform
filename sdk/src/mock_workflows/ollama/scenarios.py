"""Ollama raw-client mock scenarios (plan §9.2).

Each scenario runs through the real SDK + OpenInference Ollama instrumentor
with the HTTP boundary replaced by scripted responses (``fakes.py``):
deterministic content, fixed token counts, scripted failures, streamed chunks.
This is the OnboardingFulfillment shape: plain ``ollama.chat(...)`` calls
under a manual workflow root.
"""

from __future__ import annotations

import ollama

import ai_observability  # noqa: F401  (SDK must be initialized by runner)
from ..assertions import ScenarioAssertions
from ..scenario import Scenario, scenario_with_random_workflow_id
from .fakes import (
    MODEL,
    MockRateLimitError,
    chat_response,
    patched_ollama,
    stream_chunks,
)

WORKFLOW = dict(
    name="onboarding",
    client_id="client-42",
    version="v1",
    context={"channel": "hr"},
)

PROMPT = "Plan the hardware for a new hire."
ANSWER = "Laptop: ThinkPad T14; dock + dual monitors."


def _chat(*, stream: bool = False, capture_prompts: bool = False, **kwargs):
    """The raw-client call shape: ``import ollama; ollama.chat(...)``."""
    return ollama.chat(
        model=MODEL,
        messages=[{"role": "user", "content": PROMPT}],
        stream=stream,
        **kwargs,
    )


def run_chat(workflow_id: str) -> None:
    with patched_ollama(
        chat_response(ANSWER, prompt_tokens=11, completion_tokens=7)
    ):
        with ai_observability.workflow(
            **WORKFLOW, workflow_id=workflow_id, capture_prompts=True
        ):
            _chat()


def assert_chat(spans, workflow_id: str) -> list[str]:
    checks = ScenarioAssertions(spans)
    root = checks.require_single_root("onboarding")
    if root is None:
        return checks.failures
    checks.project_attr_matches_config(root)
    checks.attr_eq(root, "sdk.client_id", "client-42")
    checks.attr_eq(root, "sdk.workflow_id", workflow_id)
    checks.attr_eq(root, "session.id", workflow_id)
    checks.status_ok(root)

    llm = checks.require_span(kind="LLM", name="Chat")
    if llm is not None:
        checks.descendant_of(llm, root)
        checks.status_ok(llm)
        checks.attr_eq(llm, "llm.provider", "ollama")
        checks.attr_eq(llm, "llm.model_name", MODEL)
        checks.attr_eq(llm, "llm.token_count.prompt", 11)
        checks.attr_eq(llm, "llm.token_count.completion", 7)
        checks.attr_eq(llm, "llm.token_count.total", 18)
        checks.attr_eq(llm, "llm.input_messages.0.message.content", PROMPT)
        checks.attr_eq(llm, "llm.output_messages.0.message.content", ANSWER)
    return checks.failures


def run_chat_error(workflow_id: str) -> None:
    with patched_ollama(MockRateLimitError("429 Too Many Requests")):
        with ai_observability.workflow(**WORKFLOW, workflow_id=workflow_id):
            try:
                _chat()
            except MockRateLimitError:
                pass


def assert_chat_error(spans, workflow_id: str) -> list[str]:
    checks = ScenarioAssertions(spans)
    root = checks.require_single_root("onboarding")
    if root is None:
        return checks.failures
    llm = checks.require_span(kind="LLM", name="Chat")
    if llm is not None:
        checks.status_error(llm)
        checks.require(checks.has_exception_event(llm), "LLM span missing exception event")
        checks.attr_contains(llm, "sdk.error.type", "MockRateLimitError")
        checks.attr_eq(llm, "sdk.error.kind", "rate_limit")
        # The request side records the model, so errored calls carry it too.
        checks.attr_eq(llm, "llm.model_name", MODEL)
    checks.status_error(root)
    checks.attr_eq(root, "sdk.error.kind", "rate_limit")
    return checks.failures


def run_chat_redacted(workflow_id: str) -> None:
    """capture_prompts stays off (runner default): payloads must not export."""
    with patched_ollama(
        chat_response(ANSWER, prompt_tokens=6, completion_tokens=3)
    ):
        with ai_observability.workflow(**WORKFLOW, workflow_id=workflow_id):
            _chat()


def assert_chat_redacted(spans, workflow_id: str) -> list[str]:
    checks = ScenarioAssertions(spans)
    root = checks.require_single_root("onboarding")
    if root is None:
        return checks.failures
    checks.status_ok(root)
    llm = checks.require_span(kind="LLM", name="Chat")
    if llm is not None:
        checks.attr_absent(llm, "llm.input_messages.0.message.content")
        checks.attr_absent(llm, "llm.output_messages.0.message.content")
        checks.attr_eq(llm, "llm.token_count.prompt", 6)
        checks.attr_eq(llm, "llm.token_count.completion", 3)
    return checks.failures


def run_chat_stream(workflow_id: str) -> None:
    chunks = stream_chunks(
        ["Laptop: ", "ThinkPad T14", "; dock + dual monitors."],
        prompt_tokens=9,
        completion_tokens=6,
    )
    with patched_ollama(chunks):
        with ai_observability.workflow(
            **WORKFLOW, workflow_id=workflow_id, capture_prompts=True
        ):
            for _ in _chat(stream=True):
                pass


def assert_chat_stream(spans, workflow_id: str) -> list[str]:
    checks = ScenarioAssertions(spans)
    root = checks.require_single_root("onboarding")
    if root is None:
        return checks.failures
    checks.status_ok(root)
    llm_spans = checks.spans(kind="LLM", name="Chat")
    checks.require(
        len(llm_spans) == 1,
        f"expected exactly 1 streamed LLM span, got {len(llm_spans)}",
    )
    if llm_spans:
        llm = llm_spans[0]
        checks.status_ok(llm)
        checks.attr_eq(llm, "llm.token_count.prompt", 9)
        checks.attr_eq(llm, "llm.token_count.completion", 6)
        checks.attr_eq(llm, "llm.token_count.total", 15)
        checks.attr_eq(llm, "llm.output_messages.0.message.content", ANSWER)
    return checks.failures


SCENARIOS: list[Scenario] = [
    scenario_with_random_workflow_id(
        "oll_chat",
        "ollama",
        "raw ollama.chat: LLM span with provider/model/tokens + messages",
        run_chat,
        assert_chat,
        workflow_id_base="onb-1",
    ),
    scenario_with_random_workflow_id(
        "oll_chat_error",
        "ollama",
        "429-style ResponseError: ERROR LLM span, rate_limit hint, root ERROR",
        run_chat_error,
        assert_chat_error,
        workflow_id_base="onb-1",
    ),
    scenario_with_random_workflow_id(
        "oll_chat_redacted",
        "ollama",
        "capture_prompts off: messages stripped at export, tokens kept",
        run_chat_redacted,
        assert_chat_redacted,
        workflow_id_base="onb-1",
    ),
    scenario_with_random_workflow_id(
        "oll_chat_stream",
        "ollama",
        "stream=True: one span with accumulated output and final token counts",
        run_chat_stream,
        assert_chat_stream,
        workflow_id_base="onb-1",
    ),
]
