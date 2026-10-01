"""ChromaDB mock fixtures: an in-memory client with deterministic embeddings.

The real ``chromadb`` client runs (``EphemeralClient``); only the embedding
function is a tiny deterministic keyword-count model, so scenarios need no
model download and no Chroma server. Mirrors the fake-model approach of the
LangChain/LlamaIndex/Ollama suites.
"""

from __future__ import annotations

from typing import Any

import chromadb

COLLECTION = "policies"

DOCUMENT_IDS = (
    "POL-HW-01",
    "POL-LOG-02",
    "POL-SEC-03",
)
DOCUMENTS = (
    "hardware: developers receive a high-performance workstation tier.",
    "delivery: remote hires require home delivery of all equipment.",
    "security: security keys (FIDO2) are mandatory for engineering.",
)
METADATAS = (
    {"policy_code": "POL-HW-01", "section": "workstations"},
    {"policy_code": "POL-LOG-02", "section": "logistics"},
    {"policy_code": "POL-SEC-03", "section": "credentials"},
)

# Retrieval query used by the scenarios; closest to POL-HW-01.
QUERY = "hardware workstation policy"

# ``where`` filter Chroma rejects (unknown operator) — the error scenario.
BAD_WHERE = {"policy_code": {"$bogus": "POL-HW-01"}}

_KEYWORDS = ("hardware", "delivery", "security")


class FakeEmbeddingFunction:
    """Deterministic keyword-count embedding (no model, no network).

    Implements the chromadb 1.5.x embedding-function protocol: ``__call__`` /
    ``embed_documents`` / ``embed_query`` for use, plus the config surface
    (``name``/``is_legacy``/``default_space``/``supported_spaces``/
    ``get_config``/``build_from_config``) so collection configuration stays
    non-legacy (no deprecation warnings).
    """

    def __call__(self, input):
        return [self._one(text) for text in _as_texts(input)]

    def embed_documents(self, input):
        return [self._one(text) for text in _as_texts(input)]

    def embed_query(self, input):
        if isinstance(input, str):
            return self._one(input)
        return [self._one(text) for text in _as_texts(input)]

    @classmethod
    def name(cls) -> str:
        return "aiobs-fake-embedding"

    def is_legacy(self) -> bool:
        return False

    def default_space(self) -> str:
        return "l2"

    def supported_spaces(self) -> list[str]:
        return ["l2", "cosine", "ip"]

    def get_config(self) -> dict:
        return {}

    @classmethod
    def build_from_config(cls, config: dict) -> FakeEmbeddingFunction:
        return cls()

    @staticmethod
    def _one(text: str) -> list[float]:
        lowered = text.lower()
        # +0.01 keeps zero vectors away from cosine NaN territory.
        return [float(lowered.count(keyword)) + 0.01 for keyword in _KEYWORDS]


def _as_texts(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def make_collection() -> chromadb.Collection:
    """A fresh in-memory ``policies`` collection with three fixed documents.

    ``EphemeralClient`` is a process-wide singleton, so creation has to be
    idempotent across scenarios/tests (``get_or_create`` + ``upsert``).
    """
    client = chromadb.EphemeralClient()
    collection = client.get_or_create_collection(
        name=COLLECTION, embedding_function=FakeEmbeddingFunction()
    )
    collection.upsert(
        ids=list(DOCUMENT_IDS),
        documents=list(DOCUMENTS),
        metadatas=[dict(metadata) for metadata in METADATAS],
    )
    return collection
