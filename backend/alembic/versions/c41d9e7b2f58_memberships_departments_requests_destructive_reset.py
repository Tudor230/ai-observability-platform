"""memberships, departments, requests (destructive reset)

Revision ID: c41d9e7b2f58
Revises: a445f80da69f
Create Date: 2026-09-28 10:00:00.000000

Membership-based RBAC (ADR-0006). Destructive by design: trace-derived data and
user identities are not backfilled — the org tree is rebuilt through the request
flow. Pricing is kept.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'c41d9e7b2f58'
down_revision = 'a445f80da69f'
branch_labels = None
depends_on = None

# FK-safe delete order; `pricing` is intentionally not reset.
_RESET_TABLES = (
    "alerts",
    "budgets",
    "daily_metrics",
    "cost_records",
    "spans",
    "executions",
    "workflows",
    "agents",
    "clients",
    "projects",
    "teams",
    "users",
)


def upgrade() -> None:
    for table in _RESET_TABLES:
        op.execute(f"DELETE FROM {table}")

    op.create_table(
        "departments",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_departments_name"), "departments", ["name"], unique=True)

    # Teams are empty after the reset, so NOT NULL can be added directly.
    op.add_column("teams", sa.Column("department_id", sa.String(length=32), nullable=False))
    op.create_index(op.f("ix_teams_department_id"), "teams", ["department_id"], unique=False)
    op.create_foreign_key(
        "fk_teams_department_id", "teams", "departments", ["department_id"], ["id"]
    )

    op.add_column("users", sa.Column("password_hash", sa.String(length=128), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "token_version", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
    )
    op.alter_column("users", "token_version", server_default=None)
    op.drop_column("users", "role")

    op.create_table(
        "memberships",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("scope_type", sa.String(length=20), nullable=False),
        sa.Column("scope_id", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("requested_by", sa.String(length=32), nullable=True),
        sa.Column("approved_by", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_memberships_user_id"), "memberships", ["user_id"], unique=False
    )
    op.create_index(
        "ix_memberships_scope", "memberships", ["scope_type", "scope_id"], unique=False
    )
    op.create_index(
        "uq_memberships_active",
        "memberships",
        ["user_id", "role", "scope_type", "scope_id"],
        unique=True,
        postgresql_where=sa.text("status = 'approved'"),
        postgresql_nulls_not_distinct=True,
    )

    op.create_table(
        "requests",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("requester_id", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("approver_id", sa.String(length=32), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["requester_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_requests_requester_id"), "requests", ["requester_id"], unique=False
    )
    op.create_index(op.f("ix_requests_status"), "requests", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_requests_status"), table_name="requests")
    op.drop_index(op.f("ix_requests_requester_id"), table_name="requests")
    op.drop_table("requests")

    op.drop_index("uq_memberships_active", table_name="memberships")
    op.drop_index("ix_memberships_scope", table_name="memberships")
    op.drop_index(op.f("ix_memberships_user_id"), table_name="memberships")
    op.drop_table("memberships")

    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'engineer'"),
        ),
    )
    op.alter_column("users", "role", server_default=None)
    op.drop_column("users", "token_version")
    op.drop_column("users", "password_hash")

    op.drop_constraint("fk_teams_department_id", "teams", type_="foreignkey")
    op.drop_index(op.f("ix_teams_department_id"), table_name="teams")
    op.drop_column("teams", "department_id")

    op.drop_index(op.f("ix_departments_name"), table_name="departments")
    op.drop_table("departments")
