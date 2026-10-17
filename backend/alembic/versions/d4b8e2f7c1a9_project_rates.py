"""versioned project rates (ADR-0013)

Revenue and manual cost are exec-maintained inputs for the margin view. Rows are
versions: the active rate for a day is the greatest ``effective_from <= day``
and ``(project_id, effective_from)`` is unique, so a price change never
overwrites history.

Revision ID: d4b8e2f7c1a9
Revises: c3d91b7f5a24
Create Date: 2026-10-16
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'd4b8e2f7c1a9'
down_revision = 'c3d91b7f5a24'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'project_rates',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('project_id', sa.String(length=32), nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.Column('revenue_amount', sa.Numeric(18, 6), nullable=False),
        sa.Column('revenue_period', sa.String(length=16), nullable=False),
        sa.Column('manual_cost_amount', sa.Numeric(18, 6), nullable=False),
        sa.Column('manual_cost_period', sa.String(length=16), nullable=False),
        sa.Column('currency', sa.String(length=8), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_by', sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'project_id', 'effective_from', name='uq_project_rate_version'
        ),
    )
    op.create_index('ix_project_rates_project_id', 'project_rates', ['project_id'])


def downgrade() -> None:
    op.drop_index('ix_project_rates_project_id', table_name='project_rates')
    op.drop_table('project_rates')
