"""alert delivery history

Revision ID: e5c1a9f3b7d2
Revises: d7a9c4e21f68
Create Date: 2026-10-12
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'e5c1a9f3b7d2'
down_revision = 'd7a9c4e21f68'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'alert_deliveries',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('alert_id', sa.String(length=32), nullable=True),
        sa.Column('channel_id', sa.String(length=32), nullable=True),
        sa.Column('channel_type', sa.String(length=20), nullable=False),
        sa.Column('target', sa.String(length=320), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_alert_deliveries_alert_id', 'alert_deliveries', ['alert_id'])
    op.create_index('ix_alert_deliveries_channel_id', 'alert_deliveries', ['channel_id'])
    op.create_index('ix_alert_deliveries_status', 'alert_deliveries', ['status'])
    op.create_index('ix_alert_deliveries_created_at', 'alert_deliveries', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_alert_deliveries_created_at', table_name='alert_deliveries')
    op.drop_index('ix_alert_deliveries_status', table_name='alert_deliveries')
    op.drop_index('ix_alert_deliveries_channel_id', table_name='alert_deliveries')
    op.drop_index('ix_alert_deliveries_alert_id', table_name='alert_deliveries')
    op.drop_table('alert_deliveries')
