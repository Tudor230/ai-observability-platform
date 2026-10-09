"""SQLAlchemy ORM models for the platform (see plans/backend.md §5)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# Membership vocabulary (ADR-0006): a role is only meaningful with a scope.
ROLES = ("admin", "exec", "manager", "engineer", "client")
SCOPE_TYPES = ("global", "department", "team", "project")
# Role → scope matrix (plans/roles.md §3.3).
ROLE_SCOPES: dict[str, tuple[str, ...]] = {
    "admin": ("global",),
    "exec": ("global",),
    "manager": ("department", "team"),
    "engineer": ("team",),
    "client": ("project",),
}


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    department_id: Mapped[str] = mapped_column(
        ForeignKey("departments.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    department: Mapped[Department] = relationship()


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    team_id: Mapped[str] = mapped_column(
        ForeignKey("teams.id"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    team: Mapped[Team] = relationship()


class ProjectKey(Base):
    """Ingest credential for a project (ADR-0007); several keys may be active."""

    __tablename__ = "project_keys"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id"), nullable=False, index=True
    )
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    # Last 4 plaintext chars, for redacted display in the dashboard.
    key_hint: Mapped[str | None] = mapped_column(String(8), nullable=True)
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Soft revocation: revoked keys stop authenticating but stay for audit.
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    project: Mapped[Project] = relationship()


class User(Base):
    """Platform user identity (ADR-0006): roles live in memberships, not here."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    api_key_hash: Mapped[str] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Membership(Base):
    """A role granted to a user within a scope (ADR-0006, plans/roles.md §3)."""

    __tablename__ = "memberships"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20))
    scope_type: Mapped[str] = mapped_column(String(20))  # global|department|team|project
    # Polymorphic pointer to departments/teams/projects.id; NULL for global scope.
    scope_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="approved")  # approved|revoked
    requested_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_memberships_scope", "scope_type", "scope_id"),
        # One active grant per (user, role, scope); NULLS NOT DISTINCT so global
        # scope (scope_id NULL) is deduplicated too.
        Index(
            "uq_memberships_active",
            "user_id",
            "role",
            "scope_type",
            "scope_id",
            unique=True,
            postgresql_where=text("status = 'approved'"),
            postgresql_nulls_not_distinct=True,
        ),
    )


class AccessRequest(Base):
    """Self-service request for an org unit or membership (plans/roles.md §5)."""

    __tablename__ = "requests"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    type: Mapped[str] = mapped_column(String(30))
    requester_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    payload: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    approver_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    external_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160))
    version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), index=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_agent_project_name"),
    )


class Execution(Base):
    __tablename__ = "executions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    trace_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    workflow_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id"), nullable=False, index=True
    )
    client_id: Mapped[str | None] = mapped_column(
        ForeignKey("clients.id"), nullable=True, index=True
    )
    workflow_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    workflow_ref: Mapped[str | None] = mapped_column(
        ForeignKey("workflows.id"), nullable=True
    )
    workflow_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ok", index=True)
    root_error_kind: Mapped[str | None] = mapped_column(String(40), nullable=True)
    root_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(nullable=True)
    total_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    llm_calls: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    retrieval_calls: Mapped[int] = mapped_column(Integer, default=0)
    agent_calls: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    unpriced_calls: Mapped[int] = mapped_column(Integer, default=0)

    spans = relationship("Span", back_populates="execution")


class Span(Base):
    __tablename__ = "spans"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    execution_id: Mapped[str] = mapped_column(
        ForeignKey("executions.id"), nullable=False, index=True
    )
    trace_id: Mapped[str] = mapped_column(String(32), index=True)
    span_id: Mapped[str] = mapped_column(String(16), index=True)
    parent_id: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ok")
    error_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_kind: Mapped[str | None] = mapped_column(String(40), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    llm_provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    tool_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    retrieval_doc_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    attributes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    execution: Mapped[Execution] = relationship(back_populates="spans")


class Pricing(Base):
    __tablename__ = "pricing"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    provider: Mapped[str] = mapped_column(String(80), index=True)
    model: Mapped[str] = mapped_column(String(160), index=True)
    model_match: Mapped[str] = mapped_column(String(16), default="exact")  # exact|prefix
    input_price_per_1m: Mapped[float] = mapped_column(Numeric(18, 6))
    output_price_per_1m: Mapped[float] = mapped_column(Numeric(18, 6))
    cache_read_price_per_1m: Mapped[float | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    cache_write_price_per_1m: Mapped[float | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    reasoning_price_per_1m: Mapped[float | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )

    __table_args__ = (
        Index("ix_pricing_provider_model", "provider", "model"),
    )


class CostRecord(Base):
    __tablename__ = "cost_records"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    execution_id: Mapped[str] = mapped_column(
        ForeignKey("executions.id"), nullable=False, index=True
    )
    span_id: Mapped[str] = mapped_column(String(16), index=True)
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    price_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Resolved rates snapshot so cost history survives pricing edits/deletes (F30).
    unit_prices: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))


class DailyMetric(Base):
    __tablename__ = "daily_metrics"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    day: Mapped[str] = mapped_column(String(10), index=True)  # YYYY-MM-DD
    dimension: Mapped[str] = mapped_column(String(40), index=True)  # total|project|client|workflow|team
    dimension_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    executions: Mapped[int] = mapped_column(Integer, default=0)
    failed_executions: Mapped[int] = mapped_column(Integer, default=0)
    error_rate: Mapped[float] = mapped_column(Numeric(8, 4), default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    llm_calls: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    total_cost: Mapped[float] = mapped_column(Numeric(18, 6), default=0)
    avg_duration_ms: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    p50_duration_ms: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    p95_duration_ms: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    p99_duration_ms: Mapped[float] = mapped_column(Numeric(14, 2), default=0)

    __table_args__ = (
        # One row per (day, dimension, key) — prevents duplicate rollups (F26).
        # NULLS NOT DISTINCT covers the `total` dimension's NULL key.
        UniqueConstraint(
            "day",
            "dimension",
            "dimension_key",
            name="uq_daily_dim",
            postgresql_nulls_not_distinct=True,
        ),
    )


class Budget(Base):
    __tablename__ = "budgets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True, index=True
    )
    client_id: Mapped[str | None] = mapped_column(
        ForeignKey("clients.id"), nullable=True, index=True
    )
    workflow_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    # Manager-owned budgets are scoped to an org unit (audit item 5); global
    # budgets (all scope columns NULL) stay exec/admin-only.
    department_id: Mapped[str | None] = mapped_column(
        ForeignKey("departments.id"), nullable=True, index=True
    )
    team_id: Mapped[str | None] = mapped_column(
        ForeignKey("teams.id"), nullable=True, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    period: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )  # anchor/period start
    period_type: Mapped[str] = mapped_column(String(16), default="month")  # day|week|month
    name: Mapped[str | None] = mapped_column(String(160), nullable=True)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    rule_id: Mapped[str] = mapped_column(String(120), index=True)
    # The configured rule a threshold alert came from (NULL for budget alerts).
    rule_ref: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    severity: Mapped[str] = mapped_column(String(20), default="warning")
    message: Mapped[str] = mapped_column(Text)
    dimension: Mapped[str] = mapped_column(String(40))
    dimension_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, index=True
    )


class AlertRule(Base):
    """Configurable threshold rule (audit item 7); built-ins seeded from env."""

    __tablename__ = "alert_rules"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120))
    # error_rate|daily_tokens|tool_calls_per_execution|p95_latency|cost_anomaly
    metric: Mapped[str] = mapped_column(String(40))
    warning_threshold: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    critical_threshold: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    scope_type: Mapped[str] = mapped_column(String(20), default="global")
    scope_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Built-ins are deletable only when disabled (409 otherwise); they are the
    # seed of the env-threshold behavior (F04).
    builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        Index("ix_alert_rules_scope", "scope_type", "scope_id"),
        Index("ix_alert_rules_enabled", "enabled"),
    )