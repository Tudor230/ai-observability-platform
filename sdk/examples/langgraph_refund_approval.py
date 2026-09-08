#!/usr/bin/env python
"""LangGraph human-in-the-loop refund-approval demo for the ai_observability SDK.

Runs a moderately complex LangGraph ``StateGraph`` with:

* ``classify``        — LLM node that routes the request by intent
* ``check_policy``    — TOOL node (real ``@tool``) consulting the return policy
* ``draft_refund``    — LLM node that drafts a refund proposal
* ``human_approval``  — HITL ``interrupt()``: pauses and asks a human to approve
* ``finalize``        — TOOL (create_refund) + LLM node that writes the resolution
* ``status_reply``    — LLM node for order-status requests (no HITL)
* ``escalate``        — plain node for anything that needs a human agent

Conditional edges route by intent and by the human's decision, so one workflow
can produce a rich waterfall (CHAIN graph -> LLM/TOOL nodes -> HITL) and the
interrupt + resume runs group into one Phoenix **session** (``workflow_id`` =
LangGraph ``thread_id``).

The demo runs fully offline with ``--mock`` (LangChain fake model, fixed
responses/usage) or against any OpenAI-compatible endpoint without it.

Configuration (env vars, 12-factor):
    OPENAI_API_KEY       required unless --mock
    OPENAI_BASE_URL      optional; e.g. http://localhost:11434/v1 (Ollama),
                         https://api.deepseek.com, https://api.openai.com/v1
    OPENAI_MODEL         default gpt-4o-mini
    AI_OBSERVABILITY_ENDPOINT   default http://localhost:6006 (Phoenix)

Usage:
    cd sdk
    # offline, deterministic (fake model) — still exports real spans:
    uv run python examples/langgraph_refund_approval.py --mock --capture-prompts

    # real LLM against your local Phoenix:
    OPENAI_API_KEY=sk-... uv run python examples/langgraph_refund_approval.py \
        --request-id ORD-1234 --capture-prompts

    Then open http://localhost:6006 (Phoenix) -> Traces -> the "refund_approval"
    project, and follow the two traces (interrupt + resume) under one session.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from ai_observability import init, workflow

# --- pretend store data + tools -------------------------------------------------


def _build_model(mock: bool, model_name: str):
    """Real ChatOpenAI by default; a scripted fake model for --mock runs."""
    if not mock:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=model_name, temperature=0)

    from langchain_core.language_models.fake_chat_models import (
        FakeMessagesListChatModel,
    )
    from langchain_core.messages import AIMessage

    def ai(content: str, prompt_tokens: int, completion_tokens: int) -> AIMessage:
        return AIMessage(
            content=content,
            usage_metadata={
                "input_tokens": prompt_tokens,
                "output_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        )

    # Responses are consumed in node-execution order for the refund path:
    # classify -> draft_refund -> finalize (approved). Fixed usage => fixed cost.
    return FakeMessagesListChatModel(
        responses=[
            ai("refund", 12, 1),
            ai("Proposal: issue a $42.00 refund for this order.", 24, 9),
            ai("Refund approved and scheduled. Amount $42.00 will return to "
               "the original payment method in 5-7 business days.", 18, 14),
        ]
    )


@tool
def lookup_policy(query: str) -> str:
    """Look up the store's return / refund policy."""
    return (
        "Unworn items may be returned within 30 days of delivery for a full "
        "refund. Restocking fees are waived for damaged or incorrect items."
    )


@tool
def create_refund(request_id: str, amount: float) -> str:
    """Create a refund transaction for an approved request."""
    return (
        f"Refund of ${amount:.2f} for {request_id} created "
        f"(transaction REF-{request_id[-4:]})."
    )


# --- LangGraph state + nodes ----------------------------------------------------


class RefundState(TypedDict):
    request_id: str
    issue: str
    intent: str
    policy: str
    proposal: str
    approval: bool | None
    resolution: str


class RefundWorkflow:
    """Node implementations bound to a shared model instance."""

    def __init__(self, model) -> None:
        self._model = model

    def classify(self, state: RefundState) -> dict:
        reply = self._model.invoke(
            [
                SystemMessage(
                    content=(
                        "Classify the customer request as exactly one of: "
                        "refund, status, escalate."
                    )
                ),
                HumanMessage(content=state["issue"]),
            ]
        )
        text = str(reply.content).lower()
        intent = (
            "refund"
            if "refund" in text
            else "status"
            if "status" in text
            else "escalate"
        )
        return {"intent": intent}

    def route(self, state: RefundState) -> str:
        return {
            "refund": "check_policy",
            "status": "status_reply",
            "escalate": "escalate",
        }.get(state.get("intent", "escalate"), "escalate")

    def check_policy(self, state: RefundState) -> dict:
        return {"policy": lookup_policy.invoke({"query": "refund policy"})}

    def draft_refund(self, state: RefundState) -> dict:
        reply = self._model.invoke(
            [
                SystemMessage(
                    content=(
                        "Draft a one-sentence refund proposal for this request. "
                        "Reference the applicable policy."
                    )
                ),
                HumanMessage(
                    content=(
                        f"Request {state['request_id']}: {state['issue']}\n"
                        f"Policy: {state['policy']}"
                    )
                ),
            ]
        )
        return {"proposal": str(reply.content)}

    def human_approval(self, state: RefundState) -> dict:
        # Pause the graph and ask a human. The payload surfaces on
        # result["__interrupt__"] (and Phoenix via sdk.hitl.interrupt_payload).
        approved = interrupt(
            {
                "action": "approve_refund",
                "request_id": state["request_id"],
                "proposal": state["proposal"],
                "amount": 42.00,
            }
        )
        return {"approval": bool(approved)}

    def after_approval(self, state: RefundState) -> str:
        return "finalize" if state.get("approval") else "escalate"

    def finalize(self, state: RefundState) -> dict:
        if state.get("approval"):
            receipt = create_refund.invoke(
                {"request_id": state["request_id"], "amount": 42.00}
            )
            prompt = (
                f"Write the final resolution to the customer. Tool result: {receipt}"
            )
        else:
            prompt = (
                "Write a courteous message telling the customer the refund was "
                "not approved and a human agent will follow up."
            )
        reply = self._model.invoke([SystemMessage(content=prompt)])
        return {"resolution": str(reply.content)}

    def status_reply(self, state: RefundState) -> dict:
        reply = self._model.invoke(
            [
                SystemMessage(content="Answer with the order status summary."),
                HumanMessage(content=state["issue"]),
            ]
        )
        return {"resolution": str(reply.content)}

    def escalate(self, state: RefundState) -> dict:
        return {
            "resolution": (
                f"Escalated to a human agent for {state['request_id']}. "
                "A support representative will reply within 24h."
            )
        }


def build_graph(model) -> tuple:
    """Compile the refund-approval StateGraph; returns (graph, nodes)."""
    wf = RefundWorkflow(model)
    graph = (
        StateGraph(RefundState)
        .add_node("classify", wf.classify)
        .add_node("check_policy", wf.check_policy)
        .add_node("draft_refund", wf.draft_refund)
        .add_node("human_approval", wf.human_approval)
        .add_node("finalize", wf.finalize)
        .add_node("status_reply", wf.status_reply)
        .add_node("escalate", wf.escalate)
        .add_edge(START, "classify")
        .add_conditional_edges(
            "classify",
            wf.route,
            {
                "check_policy": "check_policy",
                "status_reply": "status_reply",
                "escalate": "escalate",
            },
        )
        .add_edge("check_policy", "draft_refund")
        .add_edge("draft_refund", "human_approval")
        .add_conditional_edges(
            "human_approval",
            wf.after_approval,
            {"finalize": "finalize", "escalate": "escalate"},
        )
        .add_edge("finalize", END)
        .add_edge("status_reply", END)
        .add_edge("escalate", END)
        .compile(checkpointer=InMemorySaver())
    )
    return graph, wf


# --- demo driver -----------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the LangGraph HITL refund-approval demo."
    )
    parser.add_argument("--request-id", default="ORD-1234", help="thread_id / workflow_id")
    parser.add_argument("--issue", default="I received a damaged item, I want a refund")
    parser.add_argument("--client-id", default="client-42")
    parser.add_argument("--project-id", default=os.environ.get("AI_OBSERVABILITY_PROJECT_ID", "demo"))
    parser.add_argument("--mock", action="store_true", help="use a scripted fake model (offline)")
    parser.add_argument("--capture-prompts", action="store_true", default=False)
    parser.add_argument("--auto-approve", action="store_true", help="resume with approval without prompting")
    parser.add_argument("--no-export", action="store_true", help="run without exporting (local only)")
    args = parser.parse_args()

    if not args.mock and not os.environ.get("OPENAI_API_KEY") and not os.environ.get("OPENAI_BASE_URL"):
        print(
            "No LLM credentials found. Use --mock for an offline deterministic "
            "run, or set OPENAI_API_KEY (see examples/README.md).",
            file=sys.stderr,
        )
        return 2

    init(
        api_key=os.environ.get("AI_OBSERVABILITY_API_KEY"),
        endpoint=None
        if args.no_export
        else os.environ.get("AI_OBSERVABILITY_ENDPOINT", "http://localhost:6006"),
        project_id=args.project_id,
        service_name="langgraph-refund-demo",
        service_version="1.0.0",
        deployment_environment="demo",
        capture_prompts=args.capture_prompts,
    )

    model = _build_model(args.mock, os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
    graph, _ = build_graph(model)

    thread_id = args.request_id
    config = {"configurable": {"thread_id": thread_id}}

    # --- run 1: the graph pauses at human_approval for HITL -------------------
    print(f"\n>>> starting refund-approval workflow for {thread_id} (mock={args.mock})")
    with workflow(
        name="refund_approval",
        client_id=args.client_id,
        workflow_id=thread_id,
        version="v1",
        context={"channel": "web", "ticket_id": "INC-777", "agentic": "langgraph"},
        capture_prompts=True if args.capture_prompts else None,
    ):
        result = graph.invoke(
            {"request_id": thread_id, "issue": args.issue},
            config=config,
        )

    interrupts = result.get("__interrupt__")
    if interrupts:
        ask = interrupts[0].value
        print("\n>>> HUMAN IN THE LOOP — the graph is paused waiting for a decision")
        print(f"    action   : {ask['action']}")
        print(f"    request  : {ask['request_id']}")
        print(f"    proposal : {ask['proposal']}")
        print(f"    amount   : ${ask['amount']:.2f}")
    else:
        print("\n(no interrupt this run — the request took a different path)")
        print("resolution:", result.get("resolution"))
        print("\nTrace exported. Inspect at http://localhost:6006")
        return 0

    # --- run 2: the human decides and the graph resumes -----------------------
    if args.auto_approve:
        approved = True
        print("\n>>> auto-approving (--auto-approve)")
    else:
        answer = input("\nApprove this refund? [y/N]: ").strip().lower()
        approved = answer in ("y", "yes")

    with workflow(
        name="refund_approval",
        client_id=args.client_id,
        workflow_id=thread_id,
        version="v1",
        context={"channel": "web", "ticket_id": "INC-777", "agentic": "langgraph"},
        capture_prompts=True if args.capture_prompts else None,
    ):
        final = graph.invoke(Command(resume=approved), config=config)

    print(f"\n>>> decision: {'APPROVED' if approved else 'DENIED'}")
    print("resolution:", final.get("resolution"))
    print("\nTwo traces exported (interrupt + resume) grouped under one session.")
    print("Inspect with:")
    print("  uv run python dev/inspect_traces.py")
    print("  # or open http://localhost:6006 -> Traces -> project 'demo'")
    return 0


if __name__ == "__main__":
    sys.exit(main())