"""Inspect SDK traces stored by Phoenix in PostgreSQL.

Usage:
    uv run python dev/inspect_traces.py            # latest traces + spans
    uv run python dev/inspect_traces.py --limit 5
    uv run python dev/inspect_traces.py --sql      # print sample queries instead

Connect with AI_OBSERVABILITY_PG_DSN or --dsn
(default: postgresql://postgres:postgres@localhost:5432/phoenix).
"""

from __future__ import annotations

import argparse
import os
import sys

DEFAULT_DSN = "postgresql://postgres:postgres@localhost:5432/phoenix"


def connect(dsn: str):
    import psycopg

    return psycopg.connect(dsn, autocommit=True)


def list_traces(conn, limit: int) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.trace_id,
                   s.name,
                   s.attributes->'sdk'->>'project_id'  AS project_id,
                   s.attributes->'sdk'->>'client_id'   AS client_id,
                   s.attributes->'sdk'->>'workflow_id' AS workflow_id,
                   s.attributes->'sdk'->'error'->>'kind' AS error_kind,
                   s.status_code,
                   s.start_time
            FROM spans s
            JOIN traces t ON t.id = s.trace_rowid
            WHERE s.parent_id IS NULL
            ORDER BY s.start_time DESC
            LIMIT %s
            """,
            (limit,),
        )
        columns = [c.name for c in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def trace_spans(conn, trace_id: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.span_id,
                   s.parent_id,
                   s.name,
                   s.attributes->'openinference'->'span'->>'kind' AS kind,
                   s.attributes->'llm'->'token_count'->>'prompt'  AS prompt_tokens,
                   s.attributes->'llm'->'token_count'->>'completion' AS completion_tokens,
                   s.attributes->'sdk'->'error'->>'kind'          AS error_kind,
                   s.attributes->'sdk'->'retry'->>'count'         AS retry_count,
                   s.attributes->'session'->>'id'                 AS session_id,
                   s.status_code,
                   s.start_time,
                   s.end_time
            FROM spans s
            JOIN traces t ON t.id = s.trace_rowid
            WHERE t.trace_id = %s
            ORDER BY s.start_time
            """,
            (trace_id,),
        )
        columns = [c.name for c in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def render_trace_tree(spans: list[dict]) -> list[str]:
    """Render spans as an indented tree by following parent_id links."""
    if not spans:
        return []
    by_id = {span["span_id"]: span for span in spans}
    children: dict[str, list[dict]] = {}
    for span in spans:
        children.setdefault(span["parent_id"], []).append(span)
    for key in children:
        children[key].sort(key=lambda s: s["start_time"] or 0)

    lines: list[str] = []

    def walk(span_id: str, depth: int) -> None:
        for span in children.get(span_id, []):
            lines.append(_line_for(span, depth))
            walk(span["span_id"], depth + 1)

    for root in children.get(None, []):
        lines.append(_line_for(root, 0))
        walk(root["span_id"], 1)
    return lines


def _line_for(span: dict, depth: int) -> str:
    indent = "    " * depth + ("└── " if depth else "")
    line = (
        f"{indent}{span['name']:<32} kind={span['kind'] or '-':<10} "
        f"status={span['status_code'] or '-':<6} "
        f"prompt={span['prompt_tokens'] or '-'} "
        f"completion={span['completion_tokens'] or '-'} "
        f"error={span['error_kind'] or '-'} retries={span['retry_count'] or '-'}"
    )
    return line.rstrip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.environ.get("AI_OBSERVABILITY_PG_DSN", DEFAULT_DSN))
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--trace", help="show the full span list for a trace id")
    parser.add_argument("--sql", action="store_true", help="print sample SQL and exit")
    args = parser.parse_args(argv)

    if args.sql:
        path = os.path.join(os.path.dirname(__file__), "inspect.sql")
        print(open(path).read())
        return 0

    conn = connect(args.dsn)
    if args.trace:
        spans = trace_spans(conn, args.trace)
        for line in render_trace_tree(spans):
            print("  " + line)
        print(f"{len(spans)} spans in trace {args.trace}")
        return 0

    traces = list_traces(conn, args.limit)
    if not traces:
        print("No workflow-root spans found. Did you run a scenario?")
        print("  uv run aiobs-mock --endpoint http://localhost:6006")
        return 1
    print(f"{'TRACE ID':<34} {'WORKFLOW':<24} {'PROJECT':<10} {'CLIENT':<10} {'WF ID':<12} {'STATUS':<6} FAILURE")
    for trace in traces:
        print(
            f"{trace['trace_id']:<34} {trace['name'] or '':<24} "
            f"{trace['project_id'] or '-':<10} {trace['client_id'] or '-':<10} "
            f"{trace['workflow_id'] or '-':<12} {trace['status_code'] or '-':<6} "
            f"{trace['error_kind'] or ''}"
        )
    print(f"\n{len(traces)} traces (latest first). Full spans: --trace <id>")
    return 0


if __name__ == "__main__":
    sys.exit(main())