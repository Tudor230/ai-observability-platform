"""unique project name (ADR-0012)

Revision ID: a2f7c1d94b3e
Revises: e5c1a9f3b7d2
Create Date: 2026-10-15
"""
from __future__ import annotations

from alembic import op

revision = 'a2f7c1d94b3e'
down_revision = 'e5c1a9f3b7d2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The project name becomes the unique human handle: project_id is now
    # generated and never shown (ADR-0012). Audited before the release: no
    # duplicate names exist in the dev database.
    op.create_unique_constraint('uq_projects_name', 'projects', ['name'])


def downgrade() -> None:
    op.drop_constraint('uq_projects_name', 'projects', type_='unique')
