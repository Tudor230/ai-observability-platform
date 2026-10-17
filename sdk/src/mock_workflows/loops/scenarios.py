"""Loop-detection mock scenarios (ADR-0014).

Two runs through the real SDK + OpenInference instrumentor, proving the two
halves of the feature:

* ``loop_tool_repeat`` — an agent stuck calling the same tool with the same
  arguments: signatures appear, the repeat/cycle marks land, and the workflow
  root carries the evidence counts.
* ``loop_clean_react`` — a healthy ReAct alternation with different arguments
  per step: signatures exist but nothing is ever flagged.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import tool

import ai_observability  # noqa: F401  (SDK must be initialized by runner)
from ..assertions import ScenarioAssertions
from ..scenario import Scenario, scenario_with_random_workflow_id
from ..langchain.fakes import ScriptedChatModel, ai_message, tool_calling_message

WORKFLOW = dict(name="loop_demo", version="v1")


def _build_agent(model, *, run_name: str) -> RunnableLambda:
    """A manual ReAct loop; identical follow-up prompts unless scripted
    otherwise (the stuck scenario *wants* repetition)."""

    @tool
    def lookup_stock(symbol: str) -> str:
        """Look up a stock price."""
        return f"{symbol}=42"

    def agent_loop(query: str, config: dict | None = None):
        step = model.invoke([HumanMessage(content=query)], config=config)
        while step.tool_calls:
            for call in step.tool_calls:
                lookup_stock.invoke({"symbol": call["args"]["symbol"]}, config=config)
            step = model.invoke([HumanMessage(content="continue")], config=config)
        return step

    return RunnableLambda(agent_loop).with_config({"run_name": run_name})


def run_stuck_agent(workflow_id: str) -> None:
    model = ScriptedChatModel(
        responses=[
            tool_calling_message("lookup_stock", {"symbol": "TSLA"}, 5, 9),
            tool_calling_message("lookup_stock", {"symbol": "TSLA"}, 5, 9),
            tool_calling_message("lookup_stock", {"symbol": "TSLA"}, 5, 9),
            ai_message("TSLA is $42.00", 3, 4),
        ]
    )
    agent = _build_agent(model, run_name="stuck_agent")
    with ai_observability.workflow(**WORKFLOW, workflow_id=workflow_id):
        agent.invoke("what is the price of TSLA?")


def assert_stuck_agent(spans, workflow_id: str) -> list[str]:
    checks = ScenarioAssertions(spans)
    root = checks.require_single_root("loop_demo")
    if root is None:
        return checks.failures

    tool_spans = checks.spans(kind="TOOL")
    checks.require(len(tool_spans) == 3, f"expected 3 TOOL spans, got {len(tool_spans)}")
    signatures = [checks.attrs(s)[("sdk.call.sig")] for s in tool_spans]
    checks.require(
        all(isinstance(sig, str) for sig in signatures),
        f"expected signatures on every tool call, got {signatures!r}",
    )
    checks.require(
        len(set(signatures)) == 1,
        f"expected one signature for identical calls, got {signatures!r}",
    )
    # Payload stays local: the signature rides, the argument does not.
    if tool_spans:
        checks.attr_absent(tool_spans[0], "input.value")
    marked = [s for s in tool_spans if checks.attrs(s).get("sdk.loop.signal")]
    checks.require(marked, "expected the repeated tool call to carry sdk.loop.signal")
    if marked:
        checks.require(
            "tool_repeat" in str(checks.attrs(marked[-1]).get("sdk.loop.signal")),
            f"expected a tool_repeat signal, got {checks.attrs(marked[-1]).get('sdk.loop.signal')!r}",
        )
        checks.attr_eq(marked[-1], "sdk.loop.repeat_count", 3)

    checks.attr_eq(root, "sdk.loop.tool_repeats", 3)
    checks.attr_eq(root, "sdk.loop.llm_repeats", 3)
    checks.attr_eq(root, "sdk.loop.cycle_repeats", 3)
    return checks.failures


def run_clean_react(workflow_id: str) -> None:
    model = ScriptedChatModel(
        responses=[
            tool_calling_message("lookup_stock", {"symbol": "TSLA"}, 5, 9),
            tool_calling_message("lookup_stock", {"symbol": "AAPL"}, 5, 9),
            ai_message("TSLA is $42.00, AAPL is $7.00", 3, 4),
        ]
    )
    agent = _build_agent(model, run_name="probe_agent")
    with ai_observability.workflow(**WORKFLOW, workflow_id=workflow_id):
        agent.invoke("compare TSLA and AAPL")


def assert_clean_react(spans, workflow_id: str) -> list[str]:
    checks = ScenarioAssertions(spans)
    root = checks.require_single_root("loop_demo")
    if root is None:
        return checks.failures

    tool_spans = checks.spans(kind="TOOL")
    checks.require(len(tool_spans) == 2, f"expected 2 TOOL spans, got {len(tool_spans)}")
    signatures = [checks.attrs(s).get("sdk.call.sig") for s in tool_spans]
    checks.require(
        all(isinstance(sig, str) for sig in signatures),
        f"expected signatures even on a clean run, got {signatures!r}",
    )
    checks.require(
        len(set(signatures)) == 2,
        f"different arguments must produce different signatures, got {signatures!r}",
    )
    for span in spans:
        checks.attr_absent(span, "sdk.loop.signal")
    checks.attr_absent(root, "sdk.loop.tool_repeats")
    checks.attr_absent(root, "sdk.loop.llm_repeats")
    checks.attr_absent(root, "sdk.loop.cycle_repeats")
    return checks.failures


SCENARIOS: list[Scenario] = [
    scenario_with_random_workflow_id(
        "loop_tool_repeat",
        "sdk",
        "Stuck agent: identical tool call and prompt three times",
        run=run_stuck_agent,
        assert_trace=assert_stuck_agent,
        workflow_id_base="loop-demo",
    ),
    scenario_with_random_workflow_id(
        "loop_clean_react",
        "sdk",
        "Healthy ReAct alternation with distinct arguments stays clean",
        run=run_clean_react,
        assert_trace=assert_clean_react,
        workflow_id_base="loop-clean",
    ),
]
