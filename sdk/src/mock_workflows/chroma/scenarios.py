"""ChromaDB raw-client mock scenarios (plan §9.2).

Each scenario runs through the real SDK + the SDK-owned ChromaDB interceptor
with an in-memory ``EphemeralClient`` and a deterministic embedding function
(``fakes.py``): no Chroma server, no model download. This is the
OnboardingFulfillment retrieval shape: plain ``collection.query(...)`` under a
manual workflow root.
"""

from __future__ import annotations

import ai_observability

from ..assertions import ScenarioAssertions
from ..scenario import Scenario, scenario_with_random_workflow_id
from .fakes import BAD_WHERE, COLLECTION, DOCUMENT_IDS, QUERY, make_collection

WORKFLOW = dict(
    name="onboarding",
    client_id="client-42",
    version="v1",
    context={"channel": "hr"},
)


def _query(**kwargs) -> None:
    """The raw-client call shape: ``collection.query(query_texts=[...])``."""
    collection = make_collection()
    collection.query(query_texts=[QUERY], n_results=3, **kwargs)


def run_query(workflow_id: str) -> None:
    with ai_observability.workflow(
        **WORKFLOW, workflow_id=workflow_id, capture_prompts=True
    ):
        _query()


def assert_query(spans, workflow_id: str) -> list[str]:
    checks = ScenarioAssertions(spans)
    root = checks.require_single_root("onboarding")
    if root is None:
        return checks.failures
    checks.project_attr_matches_config(root)
    checks.attr_eq(root, "sdk.client_id", "client-42")
    checks.attr_eq(root, "sdk.workflow_id", workflow_id)
    checks.status_ok(root)

    retriever = checks.require_span(kind="RETRIEVER", name="chroma.query")
    if retriever is not None:
        checks.descendant_of(retriever, root)
        checks.status_ok(retriever)
        checks.attr_eq(retriever, "db.system", "chroma")
        checks.attr_eq(retriever, "db.operation", "query")
        checks.attr_eq(retriever, "db.collection.name", COLLECTION)
        checks.attr_eq(retriever, "input.value", QUERY)
        checks.attr_eq(retriever, "chroma.query.n_results", 3)
        checks.attr_eq(retriever, "chroma.query.result_count", 3)
        checks.attr_eq(
            retriever, "retrieval.documents.0.document.id", DOCUMENT_IDS[0]
        )
        checks.attr_contains(
            retriever, "retrieval.documents.0.document.content", "workstation"
        )
        checks.attr_contains(
            retriever, "retrieval.documents.0.document.metadata", "POL-HW-01"
        )
        score = checks.attrs(retriever).get("retrieval.documents.0.document.score")
        checks.require(
            isinstance(score, float),
            f"document score = {score!r}, expected a float distance",
        )
        checks.attr_eq(retriever, "output.mime_type", "application/json")
        checks.attr_contains(retriever, "output.value", "POL-HW-01")
    return checks.failures


def run_query_error(workflow_id: str) -> None:
    with ai_observability.workflow(**WORKFLOW, workflow_id=workflow_id):
        try:
            _query(where=BAD_WHERE)
        except ValueError:
            pass


def assert_query_error(spans, workflow_id: str) -> list[str]:
    checks = ScenarioAssertions(spans)
    root = checks.require_single_root("onboarding")
    if root is None:
        return checks.failures
    retriever = checks.require_span(kind="RETRIEVER", name="chroma.query")
    if retriever is not None:
        checks.status_error(retriever)
        checks.require(
            checks.has_exception_event(retriever),
            "RETRIEVER span missing exception event",
        )
        checks.attr_contains(retriever, "sdk.error.type", "ValueError")
        # Request-side identity is recorded before the failing call.
        checks.attr_eq(retriever, "db.collection.name", COLLECTION)
    checks.status_error(root)
    return checks.failures


def run_query_redacted(workflow_id: str) -> None:
    """capture_prompts stays off (runner default): payloads must not export."""
    with ai_observability.workflow(**WORKFLOW, workflow_id=workflow_id):
        _query()


def assert_query_redacted(spans, workflow_id: str) -> list[str]:
    checks = ScenarioAssertions(spans)
    root = checks.require_single_root("onboarding")
    if root is None:
        return checks.failures
    checks.status_ok(root)
    retriever = checks.require_span(kind="RETRIEVER", name="chroma.query")
    if retriever is not None:
        checks.attr_absent(retriever, "input.value")
        checks.attr_absent(retriever, "output.value")
        checks.attr_absent(retriever, "retrieval.documents.0.document.id")
        checks.attr_absent(retriever, "retrieval.documents.0.document.content")
        checks.attr_absent(retriever, "retrieval.documents.0.document.metadata")
        checks.attr_eq(retriever, "chroma.query.result_count", 3)
    return checks.failures


SCENARIOS: list[Scenario] = [
    scenario_with_random_workflow_id(
        "chroma_query",
        "chromadb",
        "raw chromadb query: RETRIEVER span with query text + documents",
        run_query,
        assert_query,
        workflow_id_base="onb-2",
    ),
    scenario_with_random_workflow_id(
        "chroma_query_error",
        "chromadb",
        "invalid where filter: ERROR RETRIEVER span, exception event, root ERROR",
        run_query_error,
        assert_query_error,
        workflow_id_base="onb-2",
    ),
    scenario_with_random_workflow_id(
        "chroma_redacted",
        "chromadb",
        "capture_prompts off: query/documents stripped at export, count kept",
        run_query_redacted,
        assert_query_redacted,
        workflow_id_base="onb-2",
    ),
]
