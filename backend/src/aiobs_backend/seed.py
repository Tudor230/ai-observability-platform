"""Seed data: model pricing (Phoenix-compatible table) and a demo project/key.

Idempotent: skips rows that already exist.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from .db import session_scope
from .models import Pricing, Project, Team
from .security import generate_api_key, hash_api_key

# (provider, model, model_match, input/1m, output/1m, cache_read, cache_write, reasoning)
DEFAULT_PRICING: list[tuple[str, str, str, float, float, float | None, float | None, float | None]] = [
    ("openai", "gpt-4o-mini", "exact", 0.15, 0.60, 0.075, 0.15, None),
    ("openai", "gpt-4o", "exact", 2.50, 10.00, 1.25, 2.50, None),
    ("openai", "gpt-", "prefix", 2.50, 10.00, 1.25, 2.50, None),
    ("openai", "*", "default", 2.50, 10.00, 1.25, 2.50, None),
    ("anthropic", "claude", "prefix", 3.00, 15.00, 0.30, 3.00, 15.00),
    ("anthropic", "*", "default", 3.00, 15.00, 0.30, 3.00, 15.00),
    ("deepseek", "deepseek-chat", "exact", 0.27, 1.10, None, None, None),
    ("deepseek", "deepseek-reasoner", "exact", 0.55, 2.19, None, None, None),
    ("xai", "grok-", "prefix", 0.30, 1.50, None, None, None),
    ("google", "gemini-", "prefix", 0.50, 1.50, 0.50, 1.00, None),
    ("groq", "llama-", "prefix", 0.59, 0.79, None, None, None),
]


def seed_pricing() -> int:
    now = datetime.now(timezone.utc)
    added = 0
    with session_scope() as session:
        existing = set(session.execute(select(Pricing.provider, Pricing.model)).all())
        for (
            provider,
            model,
            match,
            inp,
            outp,
            cache_read,
            cache_write,
            reasoning,
        ) in DEFAULT_PRICING:
            if (provider, model) in existing:
                continue
            session.add(
                Pricing(
                    provider=provider,
                    model=model,
                    model_match=match,
                    input_price_per_1m=inp,
                    output_price_per_1m=outp,
                    cache_read_price_per_1m=cache_read,
                    cache_write_price_per_1m=cache_write,
                    reasoning_price_per_1m=reasoning,
                    effective_from=now,
                )
            )
            added += 1
    return added


def seed_demo_project(project_id: str = "proj-1", name: str = "Demo Project") -> str:
    """Create (or return) a demo project + team, minting a fresh API key hash.

    Returns the plaintext API key (shown once).
    """
    with session_scope() as session:
        project = session.execute(
            select(Project).where(Project.project_id == project_id)
        ).scalar_one_or_none()
        if project is not None:
            return "demo-key-not-returned-for-existing-project"
        team = Team(name="Platform Admins")
        session.add(team)
        session.flush()
        key = generate_api_key()
        project = Project(
            team_id=team.id,
            project_id=project_id,
            name=name,
            api_key_hash=hash_api_key(key),
            api_key_label="demo",
        )
        session.add(project)
    return key


def seed_all(project_id: str = "proj-1", project_name: str = "Demo Project") -> dict:
    pricing = seed_pricing()
    key = seed_demo_project(project_id, project_name)
    return {"pricing_added": pricing, "demo_api_key": key}