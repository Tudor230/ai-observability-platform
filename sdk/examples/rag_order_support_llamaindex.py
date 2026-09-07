#!/usr/bin/env python
"""Real (non-mocked) RAG order-support demo for the ai_observability SDK.

Runs a retrieval-augmented order-support flow with LlamaIndex against any
OpenAI-compatible chat endpoint (OpenAI, DeepSeek, Ollama, LM Studio, ...) and
exports a rich, multi-kind trace to the dev stack (Phoenix + Postgres).

The trace is deliberately layered for the MVP demo:

    CHAIN  order-support          (workflow root, sdk.* business attrs)
    ├─ CHAIN retrieve_context
    │  └─ RETRIEVER PolicyRetriever.retrieve -> _retrieve
    ├─ CHAIN lookup_order_status
    │  └─ TOOL  lookup_order      (FunctionTool call)
    ├─ CHAIN synthesize
    │  └─ CHAIN RetrieverQueryEngine.query -> _query
    │     ├─ RETRIEVER PolicyRetriever.retrieve -> _retrieve
    │     └─ CHAIN CompactAndRefine.synthesize
    │        └─ LLM  OpenAI.predict -> OpenAI.chat (tokens)
    ├─ CHAIN compose_answer
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
    OPENAI_API_KEY=sk-... uv run python examples/rag_order_support_llamaindex.py "ORD-1234"

    # inspect the trace in Postgres afterwards:
    uv run python dev/inspect_traces.py
    uv run python dev/inspect_traces.py --trace <id>
"""

from __future__ import annotations

import argparse
import os
import re
import sys

from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, TextNode
from llama_index.core.tools import FunctionTool
from llama_index.llms.openai import OpenAI

from ai_observability import init, span, workflow

# --- pretend order database + knowledge base (swap for real APIs) ------------

ORDERS = {
    "ORD-1234": {"status": "shipped", "eta": "2026-09-09", "carrier": "DHL"},
    "ORD-5678": {"status": "processing", "eta": "2026-09-12", "carrier": "UPS"},
    "ORD-9012": {"status": "delivered", "eta": "2026-09-01", "carrier": "FedEx"},
}

KNOWLEDGE_BASE = [
    TextNode(
        id_="return-policy",
        text=(
            "Return policy: unworn items may be returned within 30 days of "
            "delivery for a full refund. Return shipping is free."
        ),
    ),
    TextNode(
        id_="shipping-policy",
        text=(
            "Shipping: standard delivery is 3-5 business days; express is "
            "1-2 business days. Tracking is emailed once the order ships."
        ),
    ),
    TextNode(
        id_="payment-refund",
        text=(
            "Refunds are issued to the original payment method within 5-7 "
            "business days after the returned item is received."
        ),
    ),
]


class PolicyRetriever(BaseRetriever):
    """In-memory knowledge-base retriever (deterministic document hits).

    Subclasses ``BaseRetriever`` so the LlamaIndex instrumentor emits a
    ``RETRIEVER`` span with the retrieved nodes."""

    def _retrieve(self, query_bundle):
        terms = re.findall(r"\w+", query_bundle.query_str.lower())
        scored = []
        for doc in KNOWLEDGE_BASE:
            score = sum(1 for t in terms if t in doc.text.lower())
            if score:
                scored.append((score, doc))
        scored.sort(key=lambda item: item[0], reverse=True)
        ranked = [d for _, d in scored] or [KNOWLEDGE_BASE[0]]
        return [NodeWithScore(node=doc, score=0.95) for doc in ranked]


def lookup_order(order_id: str) -> str:
    """Look up the status and delivery ETA of a customer order."""
    order = ORDERS.get(order_id)
    if order is None:
        return f"No order found with id {order_id}"
    return (
        f"Order {order_id}: {order['status']}, "
        f"ETA {order['eta']} via {order['carrier']}"
    )


def _build_llm() -> OpenAI:
    return OpenAI(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        api_base=os.environ.get("OPENAI_BASE_URL", "http://localhost:8001/v1"),
        api_key=os.environ.get("OPENAI_API_KEY") or "demo",
        temperature=0,
    )


def run_flow(llm: OpenAI, query: str, order_id: str) -> str:
    """Layered LlamaIndex flow: retrieve -> tool -> synthesize -> validate."""
    with span("retrieve_context"):
        docs = PolicyRetriever().retrieve(query)

    with span("lookup_order_status"):
        tool = FunctionTool.from_defaults(fn=lookup_order, name="lookup_order")
        tool_result = tool.call(order_id=order_id)

    with span("synthesize"):
        engine = RetrieverQueryEngine.from_args(
            retriever=PolicyRetriever(),
            llm=llm,
        )
        answer = engine.query(query).response

    with span("compose_answer"):
        policy = "\n".join(f"- {n.node.text}" for n in docs)
        composed = (
            f"{answer}\n\n{tool_result}\n\n(Policy consulted: {policy})"
        )

    validate_response(composed, order_id)
    return composed


def validate_response(answer, order_id: str) -> None:
    """Validate the composed answer; each check is its own nested span."""
    with span("validate_response", context={"checks": 3}):
        with span("check_answer_non_empty"):
            if not answer or not str(answer).strip():
                raise RuntimeError("empty composed response")

        with span("check_mentions_order_id"):
            if order_id not in str(answer):
                raise RuntimeError(f"response does not reference order {order_id}")

        with span("check_delivery_eta"):
            if not re.search(r"\d{4}-\d{2}-\d{2}", str(answer)):
                raise RuntimeError("response does not include a delivery ETA")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the real RAG order-support demo (LlamaIndex)."
    )
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
        service_name="rag-order-support-llamaindex",
        service_version="1.0.0",
        deployment_environment="demo",
        capture_prompts=args.capture_prompts,
    )

    workflow_id = args.order_id or "ORD-1234"
    with workflow(
        name="order-support",
        client_id=args.client_id,
        workflow_id=workflow_id,
        version="v1",
        context={"channel": "web", "ticket_id": "INC-12345", "agentic": "rag", "framework": "llamaindex"},
        capture_prompts=True if args.capture_prompts else None,
    ):
        composed = run_flow(_build_llm(), args.query, workflow_id)

    print("\n--- composed response ---")
    print(composed)
    print("\nTrace exported. Inspect with:")
    print("  uv run python dev/inspect_traces.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())