#!/usr/bin/env python
"""Ollama raw-client demo for the ai_observability SDK.

Runs a plain ``ollama.chat(...)`` call — **no** LangChain/LlamaIndex wrapper —
inside a manual workflow root, with a retrieval step and a validation span, so
the trace is the exact shape an app like OnboardingFulfillment produces:
``workflow (CHAIN) -> fetch_policies (CHAIN) + Chat (LLM) + validate_plan (CHAIN)``.

With a local Ollama server it makes real calls; with ``--mock`` it scripts only
the HTTP boundary (the same fake the regression suite uses), so it runs offline
while still emitting real spans through the real instrumentor.

Configuration (env vars, 12-factor):
    AI_OBSERVABILITY_API_KEY   platform project key (the key is the identity)
    AI_OBSERVABILITY_ENDPOINT  collector URL (default http://localhost:8000)
    OLLAMA_MODEL               default granite4.2:3b

Usage:
    cd sdk

    # platform dashboard ingest, offline (no Ollama server needed):
    uv run python examples/ollama_chat.py --mock --capture-prompts \
        --endpoint http://localhost:8000 --api-key <project-api-key>

    # a real local Ollama server (http://localhost:11434):
    uv run python examples/ollama_chat.py --capture-prompts \
        --endpoint http://localhost:8000 --api-key <project-api-key>

    # Phoenix routing via the deprecated --project-id (x-project-name +
    # openinference.project.name resource attribute):
    uv run python examples/ollama_chat.py --mock --endpoint http://localhost:6006 \
        --project-id ollama-demo --capture-prompts
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import uuid

import ollama

from ai_observability import flush, init, span, workflow

PLAN_PROMPT = """You are the Enterprise Hardware & Compliance Planning Agent.
Plan the hardware for a new hire from the policy context below and answer
strictly with a JSON object:

{"hardware_provisioning": {"laptop": <str>, "peripherals": [<str>],
 "shipping_required": <bool>},
 "flagged_exceptions": [<str>], "policy_citations": [<str>]}

### CANDIDATE
Role: Backend Engineer | Department: Engineering | Work location: remote

### POLICIES
POL-HW-01: developers receive a high-performance workstation tier.
POL-LOG-02: remote hires require home delivery of all equipment.
POL-SEC-03: security keys (FIDO2) are mandatory for engineering."""

# Deterministic offline answer (valid JSON, realistic shape).
MOCK_PLAN = json.dumps(
    {
        "hardware_provisioning": {
            "laptop": 'MacBook Pro 16" (Dev Tier)',
            "peripherals": ["Dual 27\" monitors", "USB-C dock", "YubiKey 5C NFC"],
            "shipping_required": True,
        },
        "flagged_exceptions": [],
        "policy_citations": ["POL-HW-01", "POL-LOG-02", "POL-SEC-03"],
    }
)


def fetch_policies(candidate_role: str) -> list[dict]:
    """Stand-in for the app's hybrid retrieval step (chroma/BM25 in the real app).

    This is exactly where a manual ``span("fetch_policies")`` belongs when the
    retriever is not a framework the instrumentors know about.
    """
    return [
        {"code": "POL-HW-01", "title": "Workstation tiers"},
        {"code": "POL-LOG-02", "title": "Remote equipment logistics"},
        {"code": "POL-SEC-03", "title": "Security keys"},
    ]


def validate_plan(raw: str) -> dict:
    """Parse + check the model's structured output (a CHAIN span named accordingly)."""
    try:
        plan = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"model did not return valid JSON: {raw[:120]!r}") from exc
    required = {"hardware_provisioning", "flagged_exceptions", "policy_citations"}
    missing = required - set(plan)
    if missing:
        raise ValueError(f"plan is missing keys: {sorted(missing)}")
    return plan


def _ollama_server_available() -> bool:
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    if not host.startswith("http"):
        host = f"http://{host}"
    try:
        import urllib.request

        with urllib.request.urlopen(f"{host}/api/tags", timeout=2):
            return True
    except Exception:
        return False


def _chat(model: str, *, stream: bool, mock: bool) -> str:
    """One raw ``ollama.chat`` call — the instrumented surface of this demo."""
    messages = [{"role": "user", "content": PLAN_PROMPT}]

    patcher = contextlib.nullcontext()
    if mock:
        from mock_workflows.ollama.fakes import (  # dev-only: ships with the SDK
            chat_response,
            patched_ollama,
            stream_chunks,
        )

        if stream:
            cut = len(MOCK_PLAN) // 3
            chunks = stream_chunks(
                [MOCK_PLAN[:cut], MOCK_PLAN[cut : 2 * cut], MOCK_PLAN[2 * cut :]],
                prompt_tokens=312,
                completion_tokens=96,
            )
        else:
            chunks = None
        patcher = patched_ollama(
            chunks if stream else chat_response(MOCK_PLAN, prompt_tokens=312, completion_tokens=96)
        )

    with patcher:
        if stream:
            parts = [
                chunk.message.content or ""
                for chunk in ollama.chat(
                    model=model, messages=messages, stream=True, format="json"
                )
            ]
            return "".join(parts)
        response = ollama.chat(model=model, messages=messages, format="json")
        return response.message.content or ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Ollama raw-client demo.")
    parser.add_argument("--model", default=os.environ.get("OLLAMA_MODEL", "granite4.2:3b"))
    parser.add_argument("--workflow-id", default=None, help="pin the workflow_id (defaults to a random one per run)")
    parser.add_argument("--client-id", default="client-42")
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("AI_OBSERVABILITY_ENDPOINT", "http://localhost:8000"),
        help="collector URL: platform backend (:8000) or Phoenix (:6006)",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("AI_OBSERVABILITY_API_KEY"),
        help="project API key (the ingest identity; key-only is enough)",
    )
    parser.add_argument(
        "--project-id",
        default=os.environ.get("AI_OBSERVABILITY_PROJECT_ID"),
        help="optional, deprecated: Phoenix project routing only",
    )
    parser.add_argument("--mock", action="store_true", help="script the HTTP boundary (offline, no Ollama server)")
    parser.add_argument("--stream", action="store_true", help="use stream=True (chunks are reconstructed into one span)")
    parser.add_argument("--capture-prompts", action="store_true", default=False)
    parser.add_argument("--no-export", action="store_true", help="run without exporting (local only)")
    args = parser.parse_args()

    if not args.mock and not _ollama_server_available():
        print(
            f"No Ollama server reachable (model {args.model!r}). Start `ollama serve` "
            "and pull the model, or rerun with --mock for the offline demo.",
            file=sys.stderr,
        )
        return 2

    init(
        api_key=args.api_key,
        endpoint=None if args.no_export else args.endpoint,
        project_id=args.project_id,
        service_name="ollama-onboarding-demo",
        service_version="1.0.0",
        deployment_environment="demo",
        capture_prompts=args.capture_prompts,
    )

    workflow_id = args.workflow_id or f"onb-{uuid.uuid4().hex[:8]}"
    with workflow(
        name="ollama-onboarding",
        client_id=args.client_id,
        workflow_id=workflow_id,
        version="v1",
        context={"source": "ollama-demo", "mock": args.mock},
        capture_prompts=True if args.capture_prompts else None,
    ):
        with span("fetch_policies", context={"queries": 2}):
            policies = fetch_policies("Backend Engineer")
        raw = _chat(args.model, stream=args.stream, mock=args.mock)
        with span("validate_plan", context={"policies": len(policies)}):
            plan = validate_plan(raw)

    exported = flush(timeout_millis=5_000)

    print("\n--- plan ---")
    print(json.dumps(plan, indent=2))
    print(f"\nworkflow_id: {workflow_id}")
    print(f"model: {args.model} (mock={args.mock}, stream={args.stream})")
    if args.no_export:
        print("export: disabled (--no-export)")
    else:
        print(f"export: {'ok' if exported else 'FAILED — check the endpoint/API key'}")
        print(f"see the trace in the UI at {args.endpoint}: look for workflow 'ollama-onboarding'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
