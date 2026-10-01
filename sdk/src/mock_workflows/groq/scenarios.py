"""Groq raw-client mock scenarios (plan §9.2).

Each scenario runs through the real SDK + OpenInference Groq instrumentor with
the HTTP boundary replaced by scripted responses (``fakes.py``): deterministic
content, fixed token counts, scripted failures. This is the root-cause-analysis
app shape: plain ``Groq().chat.completions.create(...)`` calls under a manual
workflow root.
"""

from __future__ import annotations

import httpx
from groq import Groq, RateLimitError

import ai_observability

from ..assertions import ScenarioAssertions
from ..scenario import Scenario, scenario_with_random_workflow_id
from .fakes import MODEL, chat_completion, patched_groq, rate_limit_response

WORKFLOW = dict(
    name="rca",
    client_id="client-42",
    version="v1",
    context={"channel": "problem-management"},
)

PROMPT = "Why did incident INC-1042 come back?"
ANSWER = "Disk pressure on the DB tier after a failed batch job."


def _completion(http_client: httpx.Client):
    """The raw-client call shape: ``Groq().chat.completions.create(...)``."""
    client = Groq(
        api_key="mock",
        base_url="http://groq.mock",
        max_retries=0,
        http_client=http_client,
    )
    return client.chat.completions.create(
        model=MODEL,
        temperature=0,
        messages=[{"role": "user", "content": PROMPT}],
    )


def run_chat(workflow_id: str) -> None:
    with patched_groq(
        chat_completion(ANSWER, prompt_tokens=11, completion_tokens=7)
    ) as http_client, ai_observability.workflow(
        **WORKFLOW, workflow_id=workflow_id, capture_prompts=True
    ):
        _completion(http_client)


def assert_chat(spans, workflow_id: str) -> list[str]:
    checks = ScenarioAssertions(spans)
    root = checks.require_single_root("rca")
    if root is None:
        return checks.failures
    checks.project_attr_matches_config(root)
    checks.attr_eq(root, "sdk.client_id", "client-42")
    checks.attr_eq(root, "sdk.workflow_id", workflow_id)
    checks.status_ok(root)

    llm = checks.require_span(kind="LLM", name="Completions")
    if llm is not None:
        checks.descendant_of(llm, root)
        checks.status_ok(llm)
        checks.attr_eq(llm, "llm.provider", "groq")
        checks.attr_eq(llm, "llm.model_name", MODEL)
        checks.attr_eq(llm, "llm.token_count.prompt", 11)
        checks.attr_eq(llm, "llm.token_count.completion", 7)
        checks.attr_eq(llm, "llm.token_count.total", 18)
        checks.attr_eq(llm, "llm.input_messages.0.message.content", PROMPT)
        checks.attr_eq(llm, "llm.output_messages.0.message.content", ANSWER)
    return checks.failures


def run_chat_error(workflow_id: str) -> None:
    with patched_groq(rate_limit_response()) as http_client:
        with ai_observability.workflow(**WORKFLOW, workflow_id=workflow_id):
            try:
                _completion(http_client)
            except RateLimitError:
                pass


def assert_chat_error(spans, workflow_id: str) -> list[str]:
    checks = ScenarioAssertions(spans)
    root = checks.require_single_root("rca")
    if root is None:
        return checks.failures
    llm = checks.require_span(kind="LLM", name="Completions")
    if llm is not None:
        checks.status_error(llm)
        checks.require(checks.has_exception_event(llm), "LLM span missing exception event")
        checks.attr_contains(llm, "sdk.error.type", "RateLimitError")
        checks.attr_eq(llm, "sdk.error.kind", "rate_limit")
        checks.attr_eq(llm, "llm.provider", "groq")
    checks.status_error(root)
    checks.attr_eq(root, "sdk.error.kind", "rate_limit")
    return checks.failures


def run_chat_redacted(workflow_id: str) -> None:
    """capture_prompts stays off (runner default): payloads must not export."""
    with patched_groq(
        chat_completion(ANSWER, prompt_tokens=6, completion_tokens=3)
    ) as http_client, ai_observability.workflow(**WORKFLOW, workflow_id=workflow_id):
        _completion(http_client)


def assert_chat_redacted(spans, workflow_id: str) -> list[str]:
    checks = ScenarioAssertions(spans)
    root = checks.require_single_root("rca")
    if root is None:
        return checks.failures
    checks.status_ok(root)
    llm = checks.require_span(kind="LLM", name="Completions")
    if llm is not None:
        checks.attr_absent(llm, "input.value")
        checks.attr_absent(llm, "output.value")
        checks.attr_absent(llm, "llm.input_messages.0.message.content")
        checks.attr_absent(llm, "llm.output_messages.0.message.content")
        checks.attr_eq(llm, "llm.token_count.prompt", 6)
        checks.attr_eq(llm, "llm.token_count.completion", 3)
    return checks.failures


SCENARIOS: list[Scenario] = [
    scenario_with_random_workflow_id(
        "groq_chat",
        "groq",
        "raw groq chat completion: LLM span with provider/model/tokens + messages",
        run_chat,
        assert_chat,
        workflow_id_base="rca-1",
    ),
    scenario_with_random_workflow_id(
        "groq_chat_error",
        "groq",
        "429 rate limit: ERROR LLM span, exception event, rate_limit hint, root ERROR",
        run_chat_error,
        assert_chat_error,
        workflow_id_base="rca-1",
    ),
    scenario_with_random_workflow_id(
        "groq_redacted",
        "groq",
        "capture_prompts off: messages and IO stripped at export, tokens kept",
        run_chat_redacted,
        assert_chat_redacted,
        workflow_id_base="rca-1",
    ),
]
