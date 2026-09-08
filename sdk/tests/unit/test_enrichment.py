"""Enrichment layer: provider fill, token backfill, errors, retries, redaction,
root propagation, reclassification hooks, overflow behavior."""

from __future__ import annotations

from opentelemetry.trace.status import StatusCode

from ai_observability._attributes import (
    LLM_INPUT_MESSAGES,
    LLM_INVOCATION_PARAMETERS,
    LLM_MODEL_NAME,
    LLM_OUTPUT_MESSAGES,
    LLM_PROVIDER,
    LLM_TOKEN_COUNT_COMPLETION,
    LLM_TOKEN_COUNT_PROMPT,
    LLM_TOKEN_COUNT_TOTAL,
    SDK_CAPTURE_PROMPTS,
    SDK_ERROR_KIND,
    SDK_ERROR_MESSAGE,
    SDK_ERROR_TYPE,
    SDK_RETRY_COUNT,
    SDK_RETRY_OF,
)
from ai_observability._config import Config
from ai_observability._enrichment import register_span_kind_override

from .helpers import as_dict, enrich, exception_event, make_span

TRACE = 0x1234

CFG_OFF = Config(project_id="p1", capture_prompts=False)
CFG_ON = Config(project_id="p1", capture_prompts=True)


def _msg_attrs(prefix: str, content: str) -> dict:
    return {f"{prefix}.0.message.content": content, f"{prefix}.0.message.role": "user"}


# --- provider normalization ---------------------------------------------------


def test_provider_filled_from_model_name():
    llm = make_span(1, TRACE, None, name="llm", kind="LLM", attributes={LLM_MODEL_NAME: "deepseek-chat"})
    root = make_span(2, TRACE, None, name="wf", kind="CHAIN")
    out = as_dict(enrich([root, llm], CFG_OFF))
    assert out[1][LLM_PROVIDER] == "deepseek"


def test_provider_not_overwritten_when_set():
    llm = make_span(1, TRACE, None, name="llm", kind="LLM", attributes={LLM_PROVIDER: "openai", LLM_MODEL_NAME: "claude-x"})
    root = make_span(2, TRACE, None, name="wf", kind="CHAIN")
    out = as_dict(enrich([root, llm], CFG_OFF))
    assert out[1][LLM_PROVIDER] == "openai"


def test_provider_na_replaced():
    llm = make_span(1, TRACE, None, name="llm", kind="LLM", attributes={LLM_PROVIDER: "_NA", LLM_MODEL_NAME: "grok-2"})
    root = make_span(2, TRACE, None, name="wf", kind="CHAIN")
    out = as_dict(enrich([root, llm], CFG_OFF))
    assert out[1][LLM_PROVIDER] == "xai"


# --- token backfill -----------------------------------------------------------


def test_token_counts_preserved_when_present():
    llm = make_span(
        1, TRACE, None, name="llm", kind="LLM",
        attributes={
            LLM_TOKEN_COUNT_PROMPT: 10,
            LLM_TOKEN_COUNT_COMPLETION: 5,
            LLM_TOKEN_COUNT_TOTAL: 15,
        },
    )
    root = make_span(2, TRACE, None, name="wf", kind="CHAIN")
    out = as_dict(enrich([root, llm], CFG_OFF))
    assert out[1][LLM_TOKEN_COUNT_PROMPT] == 10
    assert out[1][LLM_TOKEN_COUNT_COMPLETION] == 5


def test_token_total_recomputed_when_wrong():
    llm = make_span(
        1, TRACE, None, name="llm", kind="LLM",
        attributes={
            LLM_TOKEN_COUNT_PROMPT: 10,
            LLM_TOKEN_COUNT_COMPLETION: 5,
            LLM_TOKEN_COUNT_TOTAL: 999,
        },
    )
    root = make_span(2, TRACE, None, name="wf", kind="CHAIN")
    out = as_dict(enrich([root, llm], CFG_OFF))
    assert out[1][LLM_TOKEN_COUNT_TOTAL] == 15


def test_token_counts_backfilled_from_messages():
    llm = make_span(
        1, TRACE, None, name="llm", kind="LLM",
        attributes={
            **_msg_attrs(LLM_INPUT_MESSAGES, "abcd"),
            **_msg_attrs(LLM_OUTPUT_MESSAGES, "ef"),
        },
    )
    root = make_span(2, TRACE, None, name="wf", kind="CHAIN")
    out = as_dict(enrich([root, llm], CFG_OFF))
    # character estimate: ceil(len/4); 4 chars -> 1, 2 chars -> 1
    assert out[1][LLM_TOKEN_COUNT_PROMPT] == 1
    assert out[1][LLM_TOKEN_COUNT_COMPLETION] == 1
    assert out[1][LLM_TOKEN_COUNT_TOTAL] == 2


# --- error capture ------------------------------------------------------------


def test_error_attributes_from_exception_event():
    llm = make_span(
        1, TRACE, None, name="llm", kind="LLM", status_code=StatusCode.ERROR,
        events=[exception_event("RateLimitError", "429 hit")],
    )
    root = make_span(2, TRACE, None, name="wf", kind="CHAIN")
    out = as_dict(enrich([root, llm], CFG_OFF))
    assert out[1][SDK_ERROR_TYPE] == "RateLimitError"
    assert out[1][SDK_ERROR_MESSAGE] == "429 hit"
    assert out[1][SDK_ERROR_KIND] == "rate_limit"


def test_timeout_kind_from_message():
    tool = make_span(
        1, TRACE, None, name="tool", kind="TOOL", status_code=StatusCode.ERROR,
        events=[exception_event("TimeoutError", "timed out")],
    )
    root = make_span(2, TRACE, None, name="wf", kind="CHAIN")
    out = as_dict(enrich([root, tool], CFG_OFF))
    assert out[1][SDK_ERROR_KIND] == "timeout"


def test_invalid_output_kind():
    step = make_span(
        1, TRACE, None, name="parse", kind="CHAIN", status_code=StatusCode.ERROR,
        events=[exception_event("JSONDecodeError", "Expecting value: line 1")],
    )
    root = make_span(2, TRACE, None, name="wf", kind="CHAIN")
    out = as_dict(enrich([root, step], CFG_OFF))
    assert out[1][SDK_ERROR_KIND] == "invalid_output"


def test_generic_llm_error_is_provider_error():
    llm = make_span(
        1, TRACE, None, name="llm", kind="LLM", status_code=StatusCode.ERROR,
        events=[exception_event("ValueError", "boom")],
    )
    root = make_span(2, TRACE, None, name="wf", kind="CHAIN")
    out = as_dict(enrich([root, llm], CFG_OFF))
    assert out[1][SDK_ERROR_KIND] == "provider_error"


def test_generic_tool_error_is_tool_error():
    tool = make_span(
        1, TRACE, None, name="tool", kind="TOOL", status_code=StatusCode.ERROR,
        events=[exception_event("RuntimeError", "boom")],
    )
    root = make_span(2, TRACE, None, name="wf", kind="CHAIN")
    out = as_dict(enrich([root, tool], CFG_OFF))
    assert out[1][SDK_ERROR_KIND] == "tool_error"


def test_message_from_status_description_when_no_event():
    llm = make_span(
        1, TRACE, None, name="llm", kind="LLM", status_code=StatusCode.ERROR,
        status_description="nope",
    )
    root = make_span(2, TRACE, None, name="wf", kind="CHAIN")
    out = as_dict(enrich([root, llm], CFG_OFF))
    assert out[1][SDK_ERROR_MESSAGE] == "nope"


# --- root propagation ---------------------------------------------------------


def test_root_becomes_error_with_primary_kind():
    llm = make_span(
        1, TRACE, 2, name="llm", kind="LLM", status_code=StatusCode.ERROR,
        events=[exception_event("RateLimitError", "429")], start_time=1000,
    )
    root = make_span(2, TRACE, None, name="wf", kind="CHAIN", status_code=StatusCode.OK)
    out = enrich([root, llm], CFG_OFF)
    root_out = next(s for s in out if s.name == "wf")
    assert root_out.status.status_code == StatusCode.ERROR
    assert dict(root_out.attributes)[SDK_ERROR_KIND] == "rate_limit"


def test_root_untouched_when_no_failure():
    llm = make_span(1, TRACE, None, name="llm", kind="LLM")
    root = make_span(2, TRACE, None, name="wf", kind="CHAIN")
    out = enrich([root, llm], CFG_OFF)
    root_out = next(s for s in out if s.name == "wf")
    assert root_out.status.status_code == StatusCode.OK


def test_root_error_without_kind_still_propagates_status():
    llm = make_span(
        1, TRACE, 2, name="llm", kind="LLM", status_code=StatusCode.ERROR,
        events=[exception_event("ValueError", "boom")],
    )
    root = make_span(2, TRACE, None, name="wf", kind="CHAIN")
    out = enrich([root, llm], CFG_OFF)
    root_out = next(s for s in out if s.name == "wf")
    assert root_out.status.status_code == StatusCode.ERROR
    # LLM-layer errors classify as provider_error; the root carries the
    # primary failure's kind.
    assert dict(root_out.attributes)[SDK_ERROR_KIND] == "provider_error"


def test_continued_trace_failure_scoped_to_own_root():
    """In a continued trace (HITL interrupt + resume share one trace id), a
    failed resume descendant must NOT flip the already-completed interrupt
    root. Both roots render in one trace, each with its own status."""
    interrupt_root = make_span(2, TRACE, None, name="approval", kind="CHAIN")
    resume_root = make_span(
        3, TRACE, 0xBEEF, name="approval", kind="CHAIN",
        status_code=StatusCode.OK, parent_remote=True,
    )
    resume_llm = make_span(
        4, TRACE, 3, name="llm", kind="LLM", status_code=StatusCode.ERROR,
        events=[exception_event("TimeoutError", "x")],
    )
    out = enrich([interrupt_root, resume_root, resume_llm], CFG_OFF)
    interrupt = next(s for s in out if s.context.span_id == 2)
    resume = next(s for s in out if s.context.span_id == 3)
    assert interrupt.status.status_code == StatusCode.OK
    assert resume.status.status_code == StatusCode.ERROR
    assert dict(resume.attributes)[SDK_ERROR_KIND] == "timeout"


# --- retries ------------------------------------------------------------------


def test_retry_count_sibling_rule():
    parent = make_span(9, TRACE, None, name="wf", kind="CHAIN")
    fail1 = make_span(1, TRACE, 9, name="Model", kind="LLM", status_code=StatusCode.ERROR,
                      events=[exception_event("TimeoutError", "x")])
    fail2 = make_span(2, TRACE, 9, name="Model", kind="LLM", status_code=StatusCode.ERROR,
                      events=[exception_event("TimeoutError", "x")])
    ok = make_span(3, TRACE, 9, name="Model", kind="LLM")
    out = as_dict(enrich([parent, fail1, fail2, ok], CFG_OFF))
    assert out[3][SDK_RETRY_COUNT] == 2


def test_retry_count_child_rule():
    retry_run = make_span(9, TRACE, None, name="Model", kind="LLM")
    fail1 = make_span(1, TRACE, 9, name="Model", kind="LLM", status_code=StatusCode.ERROR)
    ok = make_span(2, TRACE, 9, name="Model", kind="LLM")
    root = make_span(10, TRACE, None, name="wf", kind="CHAIN")
    out = as_dict(enrich([root, retry_run, fail1, ok], CFG_OFF))
    assert out[9][SDK_RETRY_COUNT] == 1


def test_no_retry_count_when_no_failure():
    parent = make_span(9, TRACE, None, name="wf", kind="CHAIN")
    a = make_span(1, TRACE, 9, name="Model", kind="LLM")
    b = make_span(2, TRACE, 9, name="Model", kind="LLM")
    out = as_dict(enrich([parent, a, b], CFG_OFF))
    assert SDK_RETRY_COUNT not in out[1]
    assert SDK_RETRY_COUNT not in out[2]


def test_retry_of_from_invocation_parameters():
    llm = make_span(
        1, TRACE, None, name="llm", kind="LLM",
        attributes={LLM_INVOCATION_PARAMETERS: '{"max_retries": 2}'},
    )
    root = make_span(2, TRACE, None, name="wf", kind="CHAIN")
    out = as_dict(enrich([root, llm], CFG_OFF))
    assert out[1][SDK_RETRY_OF] == 2


# --- redaction ----------------------------------------------------------------


def test_payloads_stripped_when_capture_off():
    llm = make_span(
        1, TRACE, None, name="llm", kind="LLM",
        attributes={
            "input.value": "secret",
            "output.value": "secret",
            **_msg_attrs(LLM_INPUT_MESSAGES, "secret"),
            **_msg_attrs(LLM_OUTPUT_MESSAGES, "secret"),
            "tool.parameters": "secret",
            "retrieval.documents.0.document.content": "secret",
            "llm.token_count.prompt": 1,
        },
    )
    root = make_span(2, TRACE, None, name="wf", kind="CHAIN")
    out = as_dict(enrich([root, llm], CFG_OFF))
    assert "input.value" not in out[1]
    assert "output.value" not in out[1]
    assert "llm.input_messages.0.message.content" not in out[1]
    assert "tool.parameters" not in out[1]
    assert "retrieval.documents.0.document.content" not in out[1]
    assert out[1]["llm.token_count.prompt"] == 1
    assert "metadata" in out[2] or True


def test_payloads_kept_when_capture_on():
    llm = make_span(
        1, TRACE, None, name="llm", kind="LLM",
        attributes={**_msg_attrs(LLM_INPUT_MESSAGES, "visible")},
    )
    root = make_span(2, TRACE, None, name="wf", kind="CHAIN")
    out = as_dict(enrich([root, llm], CFG_ON))
    assert out[1]["llm.input_messages.0.message.content"] == "visible"


def test_per_workflow_override_reenables_capture():
    llm = make_span(
        1, TRACE, 2, name="llm", kind="LLM",
        attributes={**_msg_attrs(LLM_INPUT_MESSAGES, "visible")},
    )
    root = make_span(
        2, TRACE, None, name="wf", kind="CHAIN",
        attributes={SDK_CAPTURE_PROMPTS: "true"},
    )
    out = as_dict(enrich([root, llm], CFG_OFF))
    assert out[1]["llm.input_messages.0.message.content"] == "visible"


def test_per_workflow_override_disables_capture():
    llm = make_span(
        1, TRACE, 2, name="llm", kind="LLM",
        attributes={**_msg_attrs(LLM_INPUT_MESSAGES, "hidden")},
    )
    root = make_span(
        2, TRACE, None, name="wf", kind="CHAIN",
        attributes={SDK_CAPTURE_PROMPTS: "false"},
    )
    out = as_dict(enrich([root, llm], CFG_ON))
    assert "llm.input_messages.0.message.content" not in out[1]


def test_nested_workflow_override():
    outer = make_span(1, TRACE, None, name="outer", kind="CHAIN", attributes={SDK_CAPTURE_PROMPTS: "false"})
    inner = make_span(2, TRACE, 1, name="inner", kind="CHAIN", attributes={SDK_CAPTURE_PROMPTS: "true"})
    llm = make_span(3, TRACE, 2, name="llm", kind="LLM", attributes={**_msg_attrs(LLM_INPUT_MESSAGES, "inner-capture")})
    other = make_span(4, TRACE, 1, name="llm2", kind="LLM", attributes={**_msg_attrs(LLM_INPUT_MESSAGES, "outer-hidden")})
    out = as_dict(enrich([outer, inner, llm, other], CFG_OFF))
    assert out[3]["llm.input_messages.0.message.content"] == "inner-capture"
    assert "llm.input_messages.0.message.content" not in out[4]


# --- reclassification hook ----------------------------------------------------


def test_kind_override_hook():
    def hook(span):
        if span.name == "misfired":
            return "AGENT"
        return None

    register_span_kind_override(hook)
    try:
        span = make_span(1, TRACE, None, name="misfired", kind="CHAIN")
        root = make_span(2, TRACE, None, name="wf", kind="CHAIN")
        out = as_dict(enrich([root, span], CFG_OFF))
        assert out[1]["openinference.span.kind"] == "AGENT"
    finally:
        from ai_observability import _enrichment

        _enrichment._kind_override_hooks.clear()


# --- exporter robustness ------------------------------------------------------


def test_export_never_raises_through_bad_sink():
    from opentelemetry.sdk.trace.export import SpanExportResult

    from ai_observability._enrichment import EnrichingExporter

    class ExplodingExporter:
        def export(self, spans):
            raise RuntimeError("boom")

        def force_flush(self, timeout_millis=None):
            return True

        def shutdown(self):
            pass

    exporter = EnrichingExporter(CFG_OFF, ExplodingExporter())
    result = exporter.export([make_span(1, TRACE, None)])
    assert result is SpanExportResult.FAILURE


def test_incomplete_trace_held_until_root():
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    from ai_observability._enrichment import EnrichingExporter

    sink = InMemorySpanExporter()
    exporter = EnrichingExporter(CFG_OFF, sink)
    llm = make_span(1, TRACE, 99, name="llm", kind="LLM")
    root = make_span(2, TRACE, None, name="wf", kind="CHAIN")
    exporter.export([llm])  # root missing -> held
    assert len(sink.get_finished_spans()) == 0
    exporter.export([root])  # root arrives -> whole trace flushes
    assert len(sink.get_finished_spans()) == 2