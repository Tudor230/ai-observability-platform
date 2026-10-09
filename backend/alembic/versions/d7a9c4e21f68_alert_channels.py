"""alert channels + rule channel links

Revision ID: d7a9c4e21f68
Revises: c9e3f2a51b7d
Create Date: 2026-10-09
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'd7a9c4e21f68'
down_revision = 'c9e3f2a51b7d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'alert_channels',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('target', sa.String(length=320), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('created_by', sa.String(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'alert_rule_channels',
        sa.Column('rule_id', sa.String(length=32), nullable=False),
        sa.Column('channel_id', sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ['rule_id'], ['alert_rules.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['channel_id'], ['alert_channels.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('rule_id', 'channel_id'),
    )


def downgrade() -> None:
    op.drop_table('alert_rule_channels')
    op.drop_table('alert_channels')
