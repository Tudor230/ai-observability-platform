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

TEST_DATABASE_URL = os.environ.get(
    "AIOBS_TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:55432/aiobs_test",
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
    for provider, model, inp, outp in (
        ("openai", "gpt-4o-mini", 0.15, 0.60),
        ("openai", "gpt-4o", 2.50, 10.00),
        ("anthropic", "claude", 3.00, 15.00),
        ("deepseek", "deepseek-chat", 0.27, 1.10),
    ):
        session.add(
            Pricing(
                provider=provider,
                model=model,
                model_match="exact",
                input_price_per_1m=inp,
                output_price_per_1m=outp,
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
    return TestClient(app)


@pytest.fixture()
def project(session_factory):
    from helpers import seed_project

    with session_factory() as session:
        proj = seed_project(session)
        session.commit()
        return proj