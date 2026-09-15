"""Concurrent upserts (F27): racing exporters must not fail on duplicate keys."""
from __future__ import annotations

import threading
import time

from sqlalchemy import func, select

from aiobs_backend.ingest.pipeline import _upsert_client
from aiobs_backend.models import Client


def test_concurrent_client_upsert_does_not_raise(session_factory, project):
    result: dict = {}
    started = threading.Event()

    def worker() -> None:
        with session_factory() as session:
            started.set()
            try:
                row = _upsert_client(session, "client-race")
                session.commit()
                result["id"] = row.id
            except Exception as exc:  # noqa: BLE001
                result["error"] = repr(exc)

    with session_factory() as first:
        _upsert_client(first, "client-race")  # uncommitted on purpose
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
            .select_from(Client)
            .where(Client.external_key == "client-race")
        ).scalar_one()
    assert count == 1
