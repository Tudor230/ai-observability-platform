"""End-to-end: SDK -> Phoenix -> PostgreSQL rows.

Requires the dev stack running (docker compose up -d --wait in sdk/dev) and
AI_OBSERVABILITY_E2E=1. Runs a mock scenario through the real OTLP exporter
and asserts the enriched spans landed in Postgres (Phoenix's own schema).
"""

from __future__ import annotations

import os
import time

import pytest
import psycopg

import ai_observability
from mock_workflows.langchain.scenarios import run_happy_path

pytestmark = pytest.mark.e2e

PG_DSN = os.environ.get(
    "AI_OBSERVABILITY_PG_DSN",
    "postgresql://postgres:postgres@localhost:5432/phoenix",
)
ENDPOINT = os.environ.get("AI_OBSERVABILITY_ENDPOINT", "http://localhost:6006")

NEEDS_E2E = os.environ.get("AI_OBSERVABILITY_E2E", "") not in ("", "0", "false")


@pytest.mark.skipif(not NEEDS_E2E, reason="set AI_OBSERVABILITY_E2E=1 and run the dev stack")
def test_mock_trace_lands_in_postgres():
    ai_observability.init(
        api_key="test-key",
        endpoint=ENDPOINT,
        project_id="proj-1",
        service_name="mock-checkout",
        capture_prompts=True,
    )
    try:
        run_happy_path()
        assert ai_observability.flush(timeout_millis=10_000)

        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                rows = _query(
                    """
                    SELECT s.name,
                           s.attributes->'sdk'->>'workflow_id' AS workflow_id,
                           s.attributes->'llm'->'token_count'->>'prompt' AS prompt_tokens,
                           s.attributes->'sdk'->>'client_id' AS client_id,
                           s.attributes->'session'->>'id' AS session_id
                    FROM spans s
                    WHERE s.name = %s
                      AND s.attributes->'sdk'->>'workflow_id' = %s
                    ORDER BY s.start_time DESC
                    LIMIT 1
                    """,
                    ("checkout", "order-123"),
                )
            except (psycopg.errors.UndefinedTable, psycopg.OperationalError):
                # Phoenix migrations may still be running on a fresh stack.
                rows = []
            if rows:
                break
            time.sleep(2)
        else:
            pytest.fail("trace not visible in Postgres after 60s")

        assert len(rows) == 1, rows
        row = rows[0]
        assert row["client_id"] == "client-42"
        assert row["session_id"] == "order-123"
        assert row["prompt_tokens"] is None  # business context rides the root span

        llm_rows = _query(
            """
            SELECT s.attributes->'llm'->'token_count'->>'prompt' AS prompt_tokens,
                   s.attributes->'llm'->'token_count'->>'completion' AS completion_tokens,
                   s.attributes->'llm'->'token_count'->>'total' AS total_tokens
            FROM spans s
            JOIN traces t ON t.id = s.trace_rowid
            WHERE t.trace_id = (
                SELECT t.trace_id FROM spans s2
                JOIN traces t ON t.id = s2.trace_rowid
                WHERE s2.attributes->'sdk'->>'workflow_id' = 'order-123'
                ORDER BY s2.start_time DESC
                LIMIT 1
            )
            AND s.attributes->'openinference'->'span'->>'kind' = 'LLM'
            """,
        )
        assert len(llm_rows) >= 2, "expected LLM spans under the workflow trace"
        assert all(r["completion_tokens"] is not None for r in llm_rows)
        assert any(r["prompt_tokens"] == "5" for r in llm_rows), "fixed token counts expected"
        assert any(r["prompt_tokens"] == "3" for r in llm_rows), "fixed token counts expected"
    finally:
        ai_observability.shutdown()


def _query(sql: str, params: tuple = ()) -> list[dict]:
    with psycopg.connect(PG_DSN, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            columns = [c.name for c in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]