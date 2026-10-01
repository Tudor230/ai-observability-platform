"""Seed data: model pricing (Phoenix-compatible table) and a demo project/key.

Idempotent: skips rows that already exist.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from .db import session_scope
from .models import Department, Membership, Pricing, Project, ProjectKey, Team, User
from .security import generate_api_key, hash_api_key, hash_password, key_hint

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
    # Groq's gpt-oss list rates (the model the RCA demo defaults to).
    ("groq", "openai/gpt-oss-120b", "exact", 0.15, 0.60, 0.075, None, None),
    ("groq", "openai/gpt-oss-20b", "exact", 0.075, 0.30, None, None, None),
    # Local runtimes are free: an explicit zero rate prices them at $0 instead
    # of leaving them unpriced (NULL). Delete the row to go back to unpriced.
    ("ollama", "*", "default", 0.0, 0.0, None, None, None),
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
    """Create (or return) a demo department + team + project, minting a key.

    Returns the plaintext API key (shown once).
    """
    with session_scope() as session:
        project = session.execute(
            select(Project).where(Project.project_id == project_id)
        ).scalar_one_or_none()
        if project is not None:
            return "demo-key-not-returned-for-existing-project"
        department = session.execute(
            select(Department).where(Department.name == "Platform")
        ).scalar_one_or_none()
        if department is None:
            department = Department(name="Platform")
            session.add(department)
            session.flush()
        team = Team(name="Platform Admins", department_id=department.id)
        session.add(team)
        session.flush()
        key = generate_api_key()
        project = Project(team_id=team.id, project_id=project_id, name=name)
        session.add(project)
        session.flush()
        session.add(
            ProjectKey(
                project_id=project.id,
                key_hash=hash_api_key(key),
                key_hint=key_hint(key),
                label="demo",
            )
        )
    return key


def seed_admin(email: str, password: str) -> dict:
    """Idempotently provision the bootstrap admin (env-driven, ADR-0006)."""
    with session_scope() as session:
        user = session.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()
        user_created = False
        if user is None:
            user = User(
                email=email,
                password_hash=hash_password(password),
                api_key_hash=hash_api_key(generate_api_key()),
            )
            session.add(user)
            session.flush()
            user_created = True
        elif not user.password_hash:
            user.password_hash = hash_password(password)
        membership = session.execute(
            select(Membership).where(
                Membership.user_id == user.id,
                Membership.role == "admin",
                Membership.scope_type == "global",
                Membership.status == "approved",
            )
        ).scalar_one_or_none()
        membership_created = False
        if membership is None:
            now = datetime.now(timezone.utc)
            session.add(
                Membership(
                    user_id=user.id,
                    role="admin",
                    scope_type="global",
                    scope_id=None,
                    status="approved",
                    requested_by=user.id,
                    approved_by=user.id,
                    decided_at=now,
                )
            )
            membership_created = True
    return {
        "user_created": user_created,
        "membership_created": membership_created,
    }


def seed_all(project_id: str = "proj-1", project_name: str = "Demo Project") -> dict:
    pricing = seed_pricing()
    key = seed_demo_project(project_id, project_name)
    return {"pricing_added": pricing, "demo_api_key": key}