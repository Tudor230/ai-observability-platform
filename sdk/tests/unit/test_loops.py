"""Loop detection (ADR-0014): signatures, repeats, cycles, retry exclusion.

The shared scan algorithm lives in ``aiobs_contracts``; these tests cover the
SDK's live measurement through the enrichment layer plus the signature rules.
"""

from __future__ import annotations

from opentelemetry.trace.status import StatusCode

from ai_observability._attributes import (
    INPUT_VALUE,
    LLM_MODEL_NAME,
    OPENINFERENCE_SPAN_KIND,
    SDK_CALL_SIG,
    SDK_LOOP_CYCLE_REPEATS,
    SDK_LOOP_LLM_REPEATS,
    SDK_LOOP_REPEAT_COUNT,
    SDK_LOOP_SIGNAL,
    SDK_LOOP_TOOL_REPEATS,
    SDK_RETRY_COUNT,
    TOOL_NAME,
    TOOL_PARAMETERS,
    LoopStep,
    scan_loop_steps,
)
from ai_observability._config import Config
from ai_observability._signature import call_signature

from .helpers import as_dict, enrich, make_span

TRACE = 0x77AA
CFG_OFF = Config(project_id="p1", capture_prompts=False)
CFG_NO_LOOPS = Config(project_id="p1", capture_prompts=False, loop_detection=False)


def _tool_attrs(tool: str, args: str = '{"symbol": "TSLA"}') -> dict:
    return {TOOL_NAME: tool, INPUT_VALUE: args}


def _llm_attrs(prompt: str, model: str = "fake-model") -> dict:
    return {INPUT_VALUE: prompt, LLM_MODEL_NAME: model}


def _root(span_id: int = 900):
    return make_span(span_id, TRACE, None, name="wf", kind="CHAIN", start_time=0)


# --- the shared scan algorithm -------------------------------------------------


def _step(kind: str, name: str, sig: str | None) -> LoopStep:
    return LoopStep(kind=kind, name=name, sig=sig)


def test_scan_react_alternation_is_not_a_cycle():
    steps = [
        _step("LLM", "model", "a1"),
        _step("TOOL", "search", "b1"),
        _step("LLM", "model", "a2"),
        _step("TOOL", "search", "b2"),
        _step("LLM", "model", "a3"),
        _step("TOOL", "search", "b3"),
    ]
    scan = scan_loop_steps(steps)
    assert scan.cycle_repeats == 0
    assert scan.cycle_steps == ()
    assert scan.signals() == []


def test_scan_identical_cycle_trips_all_signals():
    steps = [_step("LLM", "model", "a"), _step("TOOL", "search", "b")] * 3
    scan = scan_loop_steps(steps)
    assert scan.cycle_repeats == 3
    assert scan.cycle_steps == ("model", "search")
    assert scan.signals() == ["tool_repeat", "llm_repeat", "cycle"]


def test_scan_missing_signatures_never_match():
    steps = [_step("TOOL", "t", None), _step("TOOL", "t", None), _step("TOOL", "t", None)]
    scan = scan_loop_steps(steps)
    assert scan.tool_repeats == 0
    assert scan.cycle_repeats == 0


# --- signature rules -----------------------------------------------------------


def test_signature_requires_usable_input():
    assert call_signature("TOOL", {TOOL_NAME: "t"}) is None
    assert call_signature("LLM", {LLM_MODEL_NAME: "m"}) is None
    assert call_signature("CHAIN", {INPUT_VALUE: "x"}) is None


def test_signature_normalizes_json_key_order():
    first = call_signature("TOOL", {TOOL_NAME: "t", TOOL_PARAMETERS: '{"a": 1, "b": 2}'})
    second = call_signature("TOOL", {TOOL_NAME: "t", TOOL_PARAMETERS: '{"b": 2, "a": 1}'})
    assert first is not None and first == second


def test_signature_differs_for_different_inputs():
    first = call_signature("TOOL", _tool_attrs("t", '{"symbol": "TSLA"}'))
    second = call_signature("TOOL", _tool_attrs("t", '{"symbol": "AAPL"}'))
    assert first is not None and first != second


# --- live measurement through the enrichment layer ------------------------------


def test_repeated_tool_call_marks_third_and_root():
    spans = [
        _root(),
        make_span(1, TRACE, 900, name="lookup_stock", kind="TOOL", attributes=_tool_attrs("lookup_stock")),
        make_span(2, TRACE, 900, name="lookup_stock", kind="TOOL", attributes=_tool_attrs("lookup_stock")),
        make_span(3, TRACE, 900, name="lookup_stock", kind="TOOL", attributes=_tool_attrs("lookup_stock")),
    ]
    out = as_dict(enrich(spans, CFG_OFF))

    assert out[1][SDK_CALL_SIG] == out[2][SDK_CALL_SIG] == out[3][SDK_CALL_SIG]
    assert SDK_LOOP_SIGNAL not in out[1]
    assert SDK_LOOP_SIGNAL not in out[2]
    assert out[3][SDK_LOOP_SIGNAL] == "tool_repeat"
    assert out[3][SDK_LOOP_REPEAT_COUNT] == 3
    # Payload stripped, signature kept: the equality token is not payload.
    assert INPUT_VALUE not in out[3]
    assert out[900][SDK_LOOP_TOOL_REPEATS] == 3
    assert out[900][SDK_LOOP_LLM_REPEATS] == 0
    assert out[900][SDK_LOOP_CYCLE_REPEATS] == 0


def test_different_tool_args_do_not_repeat():
    spans = [
        _root(),
        make_span(1, TRACE, 900, name="t", kind="TOOL", attributes=_tool_attrs("t", '{"q": 1}')),
        make_span(2, TRACE, 900, name="t", kind="TOOL", attributes=_tool_attrs("t", '{"q": 2}')),
        make_span(3, TRACE, 900, name="t", kind="TOOL", attributes=_tool_attrs("t", '{"q": 3}')),
    ]
    out = as_dict(enrich(spans, CFG_OFF))
    assert SDK_LOOP_SIGNAL not in out[3]
    assert SDK_LOOP_TOOL_REPEATS not in out[900]


def test_repeated_llm_call_trips_llm_signal():
    attrs = _llm_attrs("same prompt")
    spans = [
        _root(),
        make_span(1, TRACE, 900, name="model", kind="LLM", attributes=dict(attrs)),
        make_span(2, TRACE, 900, name="model", kind="LLM", attributes=dict(attrs)),
        make_span(3, TRACE, 900, name="model", kind="LLM", attributes=dict(attrs)),
    ]
    out = as_dict(enrich(spans, CFG_OFF))
    assert out[3][SDK_LOOP_SIGNAL] == "llm_repeat"
    assert out[900][SDK_LOOP_LLM_REPEATS] == 3


def test_signature_equal_cycle_trips_cycle_signal():
    spans = [_root()]
    for index in range(3):
        spans.append(
            make_span(10 + index * 2, TRACE, 900, name="model", kind="LLM",
                      attributes=_llm_attrs("p"), start_time=(index * 2) * 10)
        )
        spans.append(
            make_span(11 + index * 2, TRACE, 900, name="search", kind="TOOL",
                      attributes=_tool_attrs("search", '{"q": "x"}'), start_time=(index * 2 + 1) * 10)
        )
    out = as_dict(enrich(spans, CFG_OFF))
    last = out[15]
    assert "cycle" in last[SDK_LOOP_SIGNAL]
    assert out[900][SDK_LOOP_CYCLE_REPEATS] == 3


def test_react_alternation_stays_clean_end_to_end():
    spans = [_root()]
    for index in range(3):
        spans.append(
            make_span(20 + index * 2, TRACE, 900, name="model", kind="LLM",
                      attributes=_llm_attrs(f"p{index}"), start_time=(index * 2) * 10)
        )
        spans.append(
            make_span(21 + index * 2, TRACE, 900, name="search", kind="TOOL",
                      attributes=_tool_attrs("search", f'{{"q": "x{index}"}}'), start_time=(index * 2 + 1) * 10)
        )
    out = as_dict(enrich(spans, CFG_OFF))
    assert all(SDK_LOOP_SIGNAL not in attrs for attrs in out.values())
    assert SDK_LOOP_TOOL_REPEATS not in out[900]


def test_retried_calls_are_excluded_from_counters():
    spans = [
        _root(),
        make_span(1, TRACE, 900, name="flaky", kind="TOOL", status_code=StatusCode.ERROR,
                  attributes=_tool_attrs("flaky")),
        make_span(2, TRACE, 900, name="flaky", kind="TOOL", status_code=StatusCode.ERROR,
                  attributes=_tool_attrs("flaky")),
        make_span(3, TRACE, 900, name="flaky", kind="TOOL", attributes=_tool_attrs("flaky")),
    ]
    out = as_dict(enrich(spans, CFG_OFF))
    assert out[3][SDK_RETRY_COUNT] == 2
    assert SDK_CALL_SIG not in out[3]
    assert SDK_LOOP_SIGNAL not in out[3]
    assert SDK_LOOP_TOOL_REPEATS not in out[900]


def test_loop_detection_can_be_disabled():
    spans = [
        _root(),
        make_span(1, TRACE, 900, name="t", kind="TOOL", attributes=_tool_attrs("t")),
        make_span(2, TRACE, 900, name="t", kind="TOOL", attributes=_tool_attrs("t")),
        make_span(3, TRACE, 900, name="t", kind="TOOL", attributes=_tool_attrs("t")),
    ]
    out = as_dict(enrich(spans, CFG_NO_LOOPS))
    assert all(SDK_CALL_SIG not in attrs for attrs in out.values())
    assert all(SDK_LOOP_SIGNAL not in attrs for attrs in out.values())
    assert SDK_LOOP_TOOL_REPEATS not in out[900]


def test_calls_without_input_are_skipped():
    spans = [
        _root(),
        make_span(1, TRACE, 900, name="t", kind="TOOL", attributes={TOOL_NAME: "t"}),
        make_span(2, TRACE, 900, name="t", kind="TOOL", attributes={TOOL_NAME: "t"}),
        make_span(3, TRACE, 900, name="t", kind="TOOL", attributes={TOOL_NAME: "t"}),
    ]
    out = as_dict(enrich(spans, CFG_OFF))
    assert all(SDK_CALL_SIG not in attrs for attrs in out.values())
    assert SDK_LOOP_TOOL_REPEATS not in out[900]


def test_root_evidence_respects_single_root_scope():
    """Root evidence is stamped on the workflow root, not on unrelated CHAINs."""
    spans = [
        _root(),
        make_span(50, TRACE, 900, name="step", kind="CHAIN"),
        make_span(1, TRACE, 50, name="t", kind="TOOL", attributes=_tool_attrs("t")),
        make_span(2, TRACE, 50, name="t", kind="TOOL", attributes=_tool_attrs("t")),
        make_span(3, TRACE, 50, name="t", kind="TOOL", attributes=_tool_attrs("t")),
    ]
    out = as_dict(enrich(spans, CFG_OFF))
    assert out[900][SDK_LOOP_TOOL_REPEATS] == 3
    assert SDK_LOOP_TOOL_REPEATS not in out[50]


def test_openinference_kind_guard_ignores_non_call_spans():
    """RETRIEVER spans (not in scope) never get signatures."""
    retriever = make_span(1, TRACE, 900, name="retriever", kind="RETRIEVER",
                          attributes={INPUT_VALUE: "same query"})
    out = as_dict(enrich([_root(), retriever], CFG_OFF))
    assert SDK_CALL_SIG not in out[1]
    assert (out[1][OPENINFERENCE_SPAN_KIND] if OPENINFERENCE_SPAN_KIND in out[1] else None) == "RETRIEVER"
