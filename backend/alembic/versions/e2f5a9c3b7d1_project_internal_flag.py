"""internal projects need no revenue (ADR-0013)

Internal work (tooling, R&D, demos) serves the org itself. Flagging it keeps its
AI cost out of the margin comparison and reports it separately, so internal
spend never reads as a loss.

Revision ID: e2f5a9c3b7d1
Revises: d4b8e2f7c1a9
Create Date: 2026-10-16
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'e2f5a9c3b7d1'
down_revision = 'd4b8e2f7c1a9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'projects',
        sa.Column(
            'internal',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column('projects', 'internal')
