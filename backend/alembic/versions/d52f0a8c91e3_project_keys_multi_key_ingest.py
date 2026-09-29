"""project_keys: multiple ingest keys per project

Revision ID: d52f0a8c91e3
Revises: c41d9e7b2f58
Create Date: 2026-09-28 14:00:00.000000

Replaces the single ``projects.api_key_hash``/``api_key_label`` credential with
a ``project_keys`` table so a project can hold several named keys; keys are
soft-revoked rather than deleted (ADR-0007). Existing hashes are carried over
(their plaintext hint cannot be recovered, so ``key_hint`` stays NULL).
"""
from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa


revision = 'd52f0a8c91e3'
down_revision = 'c41d9e7b2f58'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_keys",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("key_hash", sa.String(length=128), nullable=False),
        sa.Column("key_hint", sa.String(length=8), nullable=True),
        sa.Column("label", sa.String(length=120), nullable=True),
        sa.Column("created_by", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_project_keys_project_id"),
        "project_keys",
        ["project_id"],
        unique=False,
    )

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, api_key_hash, api_key_label, created_at FROM projects "
            "WHERE api_key_hash IS NOT NULL"
        )
    ).fetchall()
    for project_id, key_hash, label, created_at in rows:
        bind.execute(
            sa.text(
                "INSERT INTO project_keys "
                "(id, project_id, key_hash, key_hint, label, created_by, created_at) "
                "VALUES (:id, :project_id, :key_hash, NULL, :label, NULL, :created_at)"
            ),
            {
                "id": uuid.uuid4().hex,
                "project_id": project_id,
                "key_hash": key_hash,
                "label": label,
                "created_at": created_at,
            },
        )

    op.drop_column("projects", "api_key_label")
    op.drop_column("projects", "api_key_hash")


def downgrade() -> None:
    op.add_column(
        "projects", sa.Column("api_key_hash", sa.String(length=128), nullable=True)
    )
    op.add_column(
        "projects", sa.Column("api_key_label", sa.String(length=120), nullable=True)
    )

    # Carry one credential per project back into the legacy single-key column.
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT project_id, key_hash, label FROM project_keys "
            "WHERE revoked_at IS NULL ORDER BY created_at"
        )
    ).fetchall()
    seen: set[str] = set()
    for project_id, key_hash, label in rows:
        if project_id in seen:
            continue
        seen.add(project_id)
        bind.execute(
            sa.text(
                "UPDATE projects SET api_key_hash = :key_hash, api_key_label = :label "
                "WHERE id = :project_id"
            ),
            {"key_hash": key_hash, "label": label, "project_id": project_id},
        )

    op.drop_index(op.f("ix_project_keys_project_id"), table_name="project_keys")
    op.drop_table("project_keys")
