"""CLI runner: pass/fail report for the mock-workflow suite (plan §9.1).

By default assertions run offline against an in-memory tail exporter that
sees exactly the enriched spans OTLP would carry. When
``AI_OBSERVABILITY_ENDPOINT`` is set, the SDK also exports over OTLP to that
endpoint (e.g. the docker-compose Phoenix stack).

Exit code 0 when every scenario passes, 1 otherwise.
"""

from __future__ import annotations

import argparse
import sys

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from ai_observability import init
from ai_observability._config import ENDPOINT_ENV, _env, resolve_config
from ai_observability._tracing import build_otlp_exporter



GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aiobs-mock",
        description="Run the SDK mock-workflow scenarios and print a pass/fail report.",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        help="Run only the given scenario id (repeatable).",
    )
    parser.add_argument(
        "--endpoint",
        default=None,
        help="OTLP endpoint to also export to (default: AI_OBSERVABILITY_ENDPOINT env).",
    )
    args = parser.parse_args(argv)

    tail = InMemorySpanExporter()
    sinks: list = [tail]
    explicit_endpoint = args.endpoint or _env(ENDPOINT_ENV)
    config = resolve_config(
        {
            "endpoint": explicit_endpoint,
            "project_id": "proj-1",
            "capture_prompts": False,
        }
    )
    if explicit_endpoint:
        sinks.append(build_otlp_exporter(config))
    init(
        endpoint=explicit_endpoint,
        project_id="proj-1",
        capture_prompts=False,
        _final_exporter=sinks,
    )

    from .runner import SCENARIOS, run_all, run_scenario

    selected = [s for s in SCENARIOS if not args.scenario or s.id in args.scenario]
    results = run_all(tail) if not args.scenario else [
        run_scenario(s, tail) for s in selected
    ]

    print()
    print(f"{'SCENARIO':<28} {'FRAMEWORK':<11} {'SPANS':<6} RESULT")
    print("-" * 64)
    failed = 0
    for result in results:
        passed = result.passed
        if not passed:
            failed += 1
        mark = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
        print(f"{result.scenario.id:<28} {result.scenario.framework:<11} {result.span_count:<6} {mark}")
        if result.error:
            print(f"    error: {result.error}")
        for failure in result.failures:
            print(f"    - {failure}")
    print("-" * 64)
    print(f"{len(results) - failed}/{len(results)} scenarios passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())