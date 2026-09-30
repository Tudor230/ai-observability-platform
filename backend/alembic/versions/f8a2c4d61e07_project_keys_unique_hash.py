"""project_keys: unique key_hash for key-first ingest

Revision ID: f8a2c4d61e07
Revises: d52f0a8c91e3
Create Date: 2026-09-30 12:00:00.000000

ADR-0008 makes the API key the sole ingest identity, so a key hash must resolve
exactly one project; a unique index makes that an invariant. Keys are 256-bit
random values, so existing duplicates should not exist — the migration checks
first and fails with an actionable message instead of a raw index error.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'f8a2c4d61e07'
down_revision = 'd52f0a8c91e3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    duplicates = bind.execute(
        sa.text(
            "SELECT key_hash, count(*) AS n FROM project_keys "
            "GROUP BY key_hash HAVING count(*) > 1"
        )
    ).fetchall()
    if duplicates:
        detail = ", ".join(f"{row.key_hash[:12]}… ({row.n}x)" for row in duplicates)
        raise RuntimeError(
            "duplicate project_keys.key_hash values block the unique index "
            f"(ADR-0008): {detail}. Revoke the duplicate keys and retry."
        )
    op.create_index(
        op.f("ix_project_keys_key_hash"),
        "project_keys",
        ["key_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_project_keys_key_hash"), table_name="project_keys")
