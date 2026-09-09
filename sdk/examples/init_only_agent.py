#!/usr/bin/env python
"""Minimal-tracing demo for the ai_observability SDK: `init()` only.

The ONLY SDK usage is ``init(...)`` (and ``flush()`` at shutdown) — no
``with workflow(...)``, no ``with span(...)``. Every span in the trace is
produced by the SDK's automatic LangChain instrumentation:

    AGENT checkout_agent        (root — a RunnableLambda run)
    ├─ LLM                      (tool-calling step)
    ├─ TOOL lookup_order        (order lookup)
    └─ LLM                      (final answer, fed the tool result)

Because there is no workflow boundary, the framework spans are their own roots:
each run is its own trace in Phoenix and there are no ``sdk.*`` business
attributes. ``checkout_agent.py`` runs the same code wrapped in
``workflow()``/``span()`` boundaries.

Configuration (env vars, 12-factor):
    OPENAI_API_KEY       required by the provider client
    OPENAI_BASE_URL      optional; e.g. http://localhost:11434/v1 (Ollama),
                         https://api.deepseek.com, https://api.openai.com/v1
    OPENAI_MODEL         default gpt-4o-mini (e.g. deepseek-chat, qwen2.5:7b)
    AI_OBSERVABILITY_ENDPOINT   default http://localhost:6006 (Phoenix)

Usage:
    cd sdk
    OPENAI_API_KEY=sk-... uv run python examples/init_only_agent.py "ORD-1234"

    # inspect the trace in Postgres afterwards:
    uv run python dev/inspect_traces.py
    uv run python dev/inspect_traces.py --trace <id>
"""

from __future__ import annotations

import argparse
import os
import re
import sys

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from ai_observability import flush, init

# --- pretend order database (swap for a real API) -----------------------------

ORDERS = {
    "ORD-1234": {"status": "shipped", "eta": "2026-09-09", "carrier": "DHL"},
    "ORD-5678": {"status": "processing", "eta": "2026-09-12", "carrier": "UPS"},
    "ORD-9012": {"status": "delivered", "eta": "2026-09-01", "carrier": "FedEx"},
}


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


def build_agent(model: ChatOpenAI) -> RunnableLambda:
    """A minimal tool-calling agent loop (works on any chat-completions
    endpoint that supports the tools parameter). Wrapped as a RunnableLambda
    so the instrumentor emits an AGENT span with nested LLM/TOOL children."""

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


def check_answer_non_empty(answer) -> str:
    if not answer or not str(answer).strip():
        raise RuntimeError("empty agent response")
    return answer


def check_mentions_order_id(answer, order_id: str) -> str:
    if order_id not in str(answer):
        raise RuntimeError(f"answer does not reference order {order_id}")
    return answer


def check_delivery_eta(answer) -> str:
    if not re.search(r"\d{4}-\d{2}-\d{2}", str(answer)):
        raise RuntimeError("answer does not include a delivery ETA")
    return answer


def order_id_from_query(query: str) -> str:
    match = re.search(r"ORD-\d+", query)
    return match.group(0) if match else "ORD-1234"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the checkout-support demo.")
    parser.add_argument("query", nargs="?", default="Where is my order ORD-1234?")
    parser.add_argument("--order-id", default=None, help="order id used for lookups and validation (defaults to the order id found in the query)")
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
        service_name="checkout-support-demo",
        service_version="1.0.0",
        deployment_environment="demo",
        capture_prompts=args.capture_prompts,
    )

    model = ChatOpenAI(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0,
    )

    order_id = args.order_id or order_id_from_query(args.query)

    answer = build_agent(model).invoke(args.query)
    check_answer_non_empty(answer)
    check_mentions_order_id(answer, order_id)
    check_delivery_eta(answer)

    flush(timeout_millis=5_000)

    print("\n--- agent answer ---")
    print(answer)
    print("\nTrace exported. Inspect with:")
    print("  uv run python dev/inspect_traces.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())