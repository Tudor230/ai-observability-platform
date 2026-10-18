"""Concurrent upserts (F27): racing exporters must not fail on duplicate keys."""
from __future__ import annotations

import threading
import time

from sqlalchemy import func, select

from aiobs_backend.ingest.pipeline import _upsert_row
from aiobs_backend.models import ProjectKey

DIGEST = "race-digest-0001"


def _upsert_key(session, project, digest: str = DIGEST):
    return _upsert_row(
        session,
        ProjectKey,
        ProjectKey.key_hash == digest,
        {"project_id": project.id, "key_hash": digest, "key_hint": "abcd"},
    )


def test_concurrent_upsert_does_not_raise(session_factory, project):
    result: dict = {}
    started = threading.Event()

    def worker() -> None:
        with session_factory() as session:
            started.set()
            try:
                row, _ = _upsert_key(session, project)
                session.commit()
                result["id"] = row.id
            except Exception as exc:  # noqa: BLE001
                result["error"] = repr(exc)

    with session_factory() as first:
        _upsert_key(first, project)  # uncommitted on purpose
        thread = threading.Thread(target=worker)
        thread.start()
        assert started.wait(timeout=2)
        time.sleep(0.3)  # let the worker block on the pending insert
        first.commit()

    thread.join(timeout=10)
    assert not thread.is_alive(), "worker deadlocked"
    assert "error" not in result, result
    assert result.get("id")

    with session_factory() as session:
        count = session.execute(
            select(func.count())
            .select_from(ProjectKey)
            .where(ProjectKey.key_hash == DIGEST)
        ).scalar_one()
    assert count == 1
