#!/usr/bin/env python
"""Real (non-mocked) RAG checkout-support demo for the ai_observability SDK.

Runs a retrieval-augmented checkout-support agent against any OpenAI-compatible
chat endpoint (OpenAI, DeepSeek, Ollama, LM Studio, ...) and exports a rich,
multi-kind trace to the dev stack (Phoenix + Postgres).

The trace is deliberately layered so the MVP demo shows a varied waterfall:

    CHAIN  checkout_rag          (workflow root, sdk.* business attrs)
    ├─ CHAIN retrieve_context
    │  └─ RETRIEVER lookup_docs  (in-memory knowledge base -> retrieval.documents.*)
    ├─ CHAIN generate_answer
    │  └─ AGENT checkout_agent   (manual tool loop, RunnableLambda)
    │     ├─ LLM                (tool-calling step)
    │     ├─ TOOL lookup_order  (real order lookup)
    │     └─ LLM                (final answer, fed the tool result)
    ├─ CHAIN compose_answer     (retrieval + order status -> final response)
    └─ CHAIN validate_response
       ├─ CHAIN check_answer_non_empty
       ├─ CHAIN check_mentions_order_id
       └─ CHAIN check_delivery_eta

Configuration (env vars, 12-factor):
    OPENAI_API_KEY       required by the provider client
    OPENAI_BASE_URL      optional; e.g. http://localhost:11434/v1 (Ollama),
                         https://api.deepseek.com, https://api.openai.com/v1
    OPENAI_MODEL         default gpt-4o-mini (e.g. deepseek-chat, qwen2.5:7b)
    AI_OBSERVABILITY_ENDPOINT   default http://localhost:6006 (Phoenix)

Usage:
    cd sdk
    OPENAI_API_KEY=sk-... uv run python examples/rag_checkout_agent.py "ORD-1234"

    # inspect the trace in Postgres afterwards:
    uv run python dev/inspect_traces.py
    uv run python dev/inspect_traces.py --trace <id>
"""

from __future__ import annotations

import argparse
import os
import re
import sys

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from ai_observability import init, span, workflow

# --- pretend order database + knowledge base (swap for real APIs) ------------

ORDERS = {
    "ORD-1234": {"status": "shipped", "eta": "2026-09-09", "carrier": "DHL"},
    "ORD-5678": {"status": "processing", "eta": "2026-09-12", "carrier": "UPS"},
    "ORD-9012": {"status": "delivered", "eta": "2026-09-01", "carrier": "FedEx"},
}

KNOWLEDGE_BASE = [
    {
        "id": "return-policy",
        "text": (
            "Return policy: unworn items may be returned within 30 days of "
            "delivery for a full refund. Return shipping is free."
        ),
    },
    {
        "id": "shipping-policy",
        "text": (
            "Shipping: standard delivery is 3-5 business days; express is "
            "1-2 business days. Tracking is emailed once the order ships."
        ),
    },
    {
        "id": "payment-refund",
        "text": (
            "Refunds are issued to the original payment method within 5-7 "
            "business days after the returned item is received."
        ),
    },
]


class OrderDocsRetriever(BaseRetriever):
    """In-memory knowledge-base retriever (deterministic document hits).

    Subclasses ``BaseRetriever`` so the LangChain instrumentor emits a
    ``RETRIEVER`` span with ``retrieval.documents.*`` attributes."""

    docs: list[dict] = KNOWLEDGE_BASE

    def _get_relevant_documents(self, query, *, run_manager=None):
        terms = re.findall(r"\w+", query.lower())
        scored = []
        for doc in self.docs:
            score = sum(1 for t in terms if t in doc["text"].lower())
            if score:
                scored.append((score, doc))
        scored.sort(key=lambda item: item[0], reverse=True)
        # Always return at least one document so the demo trace is deterministic.
        ranked = [d for _, d in scored] or [self.docs[0]]
        return [Document(page_content=d["text"], id=d["id"]) for d in ranked]


@tool
def lookup_order(order_id: str) -> str:
    """Look up the status and delivery ETA of a customer order."""
    order = ORDERS.get(order_id)
    if order is None:
        return f"No order found with id {order_id}"
    return (
        f"Order {order_id}: {order['status']}, "
        f"ETA {order['eta']} via {order['carrier']}"
    )


def _retrieve_docs(query: str) -> list:
    retriever = OrderDocsRetriever()
    return retriever.invoke(query, config={"run_name": "lookup_docs"})


def _agent_step(model: ChatOpenAI) -> RunnableLambda:
    """A minimal tool-calling agent loop (works on any chat-completions
    endpoint that supports the tools parameter)."""

    def agent_loop(query: str, config: dict | None = None) -> str:
        messages = [
            SystemMessage(
                content=(
                    "You are a checkout support agent. Use the lookup_order "
                    "tool to check order status, then answer concisely."
                )
            ),
            HumanMessage(content=query),
        ]
        bound = model.bind_tools([lookup_order])
        step = bound.invoke(messages, config=config)
        if step.tool_calls:
            for call in step.tool_calls:
                tool_result = lookup_order.invoke(
                    {"order_id": call["args"]["order_id"]}, config=config
                )
                messages.append(step)
                messages.append(
                    HumanMessage(content=f"tool result: {tool_result}")
                )
            step = model.invoke(messages, config=config)
        return step.content

    return RunnableLambda(agent_loop).with_config({"run_name": "checkout_agent"})


def _compose(docs: list, answer: str) -> str:
    context = "\n".join(f"- {d.page_content}" for d in docs)
    return f"{answer}\n\n(Context consulted: {context})"


def run_rag(model: ChatOpenAI, query: str) -> str:
    """Layered RAG flow: retrieve -> agent -> compose -> validate."""
    with span("retrieve_context"):
        docs = _retrieve_docs(query)

    with span("generate_answer"):
        answer = _agent_step(model).invoke(query)

    with span("compose_answer"):
        composed = _compose(docs, answer)

    validate_response(answer, query)
    return composed


def validate_response(answer, query: str) -> None:
    """Validate the agent's answer; each check is its own nested span."""
    order_id = re.search(r"ORD-\d+", query)
    order_id = order_id.group(0) if order_id else "ORD-1234"

    with span("validate_response", context={"checks": 3}):
        with span("check_answer_non_empty"):
            if not answer or not str(answer).strip():
                raise RuntimeError("empty agent response")

        with span("check_mentions_order_id"):
            if order_id not in str(answer):
                raise RuntimeError(f"answer does not reference order {order_id}")

        with span("check_delivery_eta"):
            if not re.search(r"\d{4}-\d{2}-\d{2}", str(answer)):
                raise RuntimeError("answer does not include a delivery ETA")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the real RAG checkout-support demo.")
    parser.add_argument("query", nargs="?", default="Where is my order ORD-1234?")
    parser.add_argument("--order-id", default=None, help="business workflow_id (defaults to the order id found in the query)")
    parser.add_argument("--client-id", default="client-42")
    parser.add_argument("--project-id", default=os.environ.get("AI_OBSERVABILITY_PROJECT_ID", "demo"))
    parser.add_argument("--capture-prompts", action="store_true", default=False)
    parser.add_argument("--no-export", action="store_true", help="run without exporting (local only)")
    args = parser.parse_args()

    if not os.environ.get("OPENAI_API_KEY") and not os.environ.get("OPENAI_BASE_URL"):
        print(
            "No LLM credentials found. Set OPENAI_API_KEY (and optionally "
            "OPENAI_BASE_URL / OPENAI_MODEL). See examples/README.md.",
            file=sys.stderr,
        )
        return 2

    init(
        api_key=os.environ.get("AI_OBSERVABILITY_API_KEY"),
        endpoint=None if args.no_export else os.environ.get("AI_OBSERVABILITY_ENDPOINT", "http://localhost:6006"),
        project_id=args.project_id,
        service_name="rag-checkout-demo",
        service_version="1.0.0",
        deployment_environment="demo",
        capture_prompts=args.capture_prompts,
    )

    model = ChatOpenAI(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0,
    )

    workflow_id = args.order_id or "ORD-1234"
    with workflow(
        name="checkout_rag",
        client_id=args.client_id,
        workflow_id=workflow_id,
        version="v1",
        context={"channel": "web", "ticket_id": "INC-12345", "agentic": "rag"},
        capture_prompts=True if args.capture_prompts else None,
    ):
        composed = run_rag(model, args.query)

    print("\n--- composed response ---")
    print(composed)
    print("\nTrace exported. Inspect with:")
    print("  uv run python dev/inspect_traces.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())