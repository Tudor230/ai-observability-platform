"""Data retention purge (F35)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from aiobs_backend.models import Alert, CostRecord, DailyMetric, Execution, Span
from aiobs_backend.retention import purge_expired


def _add_execution(session, project, *, trace_id: str, started: datetime):
    row = Execution(
        trace_id=trace_id,
        project_id=project.id,
        workflow_name="wf",
        status="ok",
        started_at=started,
        ended_at=started,
    )
    session.add(row)
    session.flush()
    return row


def test_purge_removes_only_expired_rows(session_factory, project):
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=40)
    with session_factory() as session:
        expired = _add_execution(session, project, trace_id="ret-old", started=old)
        session.add(
            Span(
                execution_id=expired.id,
                trace_id="ret-old",
                span_id="a",
                kind="CHAIN",
                name="wf",
                started_at=old,
                status="ok",
            )
        )
        session.add(CostRecord(execution_id=expired.id, span_id="a", amount=0.01))
        _add_execution(session, project, trace_id="ret-new", started=now)
        session.add(
            DailyMetric(
                day=old.date().isoformat(), dimension="total", dimension_key=None
            )
        )
        session.add(
            DailyMetric(
                day=now.date().isoformat(), dimension="total", dimension_key=None
            )
        )
        session.add(
            Alert(
                rule_id="ret-test",
                severity="warning",
                message="old",
                dimension="rule",
                triggered_at=old,
            )
        )
        session.commit()

        result = purge_expired(session, retention_days=30, now=now)
        session.commit()

        assert result == {
            "executions": 1,
            "spans": 1,
            "cost_records": 1,
            "daily_metrics": 1,
            "alerts": 1,
        }
        assert [e.trace_id for e in session.execute(select(Execution)).scalars()] == [
            "ret-new"
        ]
        days = [m.day for m in session.execute(select(DailyMetric)).scalars()]
        assert days == [now.date().isoformat()]
        assert session.execute(select(Alert)).first() is None


def test_retention_zero_is_a_noop(session_factory, project):
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        _add_execution(
            session, project, trace_id="ret-keep", started=now - timedelta(days=400)
        )
        session.commit()
        result = purge_expired(session, retention_days=0, now=now)
    assert result["executions"] == 0
