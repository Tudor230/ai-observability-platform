"""Pytest fixtures: fresh PostgreSQL schema, seeded pricing/project, test app."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from aiobs_backend.db import Base
from aiobs_backend.models import Pricing

os.environ.setdefault("AIOBS_ADMIN_API_KEY", "admin")
os.environ.setdefault(
    "AIOBS_JWT_SECRET", "test-secret-0123456789abcdef0123456789abcdef"
)

TEST_DATABASE_URL = os.environ.get(
    "AIOBS_TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/aiobs_test",
)

from datetime import datetime, timezone  # noqa: E402


@pytest.fixture()
def engine():
    eng = create_engine(TEST_DATABASE_URL, future=True)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    with sessionmaker(bind=eng, expire_on_commit=False, future=True)() as session:
        _seed_pricing(session)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def _seed_pricing(session):
    now = datetime.now(timezone.utc)
    for provider, model, inp, outp, cr, cw, rz in (
        ("openai", "gpt-4o-mini", 0.15, 0.60, 0.075, 0.15, None),
        ("openai", "gpt-4o", 2.50, 10.00, 1.25, 2.50, None),
        ("anthropic", "claude", 3.00, 15.00, 0.30, 3.00, 15.00),
        ("deepseek", "deepseek-chat", 0.27, 1.10, None, None, None),
    ):
        session.add(
            Pricing(
                provider=provider,
                model=model,
                model_match="exact",
                input_price_per_1m=inp,
                output_price_per_1m=outp,
                cache_read_price_per_1m=cr,
                cache_write_price_per_1m=cw,
                reasoning_price_per_1m=rz,
                effective_from=now,
            )
        )
    # Local runtimes are free: explicit zero rate (priced $0, not unpriced).
    session.add(
        Pricing(
            provider="ollama",
            model="*",
            model_match="default",
            input_price_per_1m=0.0,
            output_price_per_1m=0.0,
            effective_from=now,
        )
    )
    session.commit()


@pytest.fixture()
def app(session_factory):
    from helpers import build_app

    return build_app(session_factory)


@pytest.fixture()
def client(app):
    """Admin-authenticated client: most tests exercise data, not auth gates."""
    return TestClient(app, headers={"x-admin-key": "admin"})


@pytest.fixture()
def anon(app):
    """Unauthenticated client for auth/scope tests (login, cookies)."""
    return TestClient(app)


@pytest.fixture()
def project(session_factory):
    from helpers import seed_project

    with session_factory() as session:
        proj = seed_project(session)
        session.commit()
        return proj