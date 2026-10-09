"""alert rules: configurable thresholds + alerts.rule_ref

Revision ID: c9e3f2a51b7d
Revises: b3f1c8a97d2e
Create Date: 2026-10-09
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'c9e3f2a51b7d'
down_revision = 'b3f1c8a97d2e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'alert_rules',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('metric', sa.String(length=40), nullable=False),
        sa.Column('warning_threshold', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('critical_threshold', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('scope_type', sa.String(length=20), nullable=False),
        sa.Column('scope_id', sa.String(length=32), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('builtin', sa.Boolean(), nullable=False),
        sa.Column('created_by', sa.String(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_alert_rules_scope', 'alert_rules', ['scope_type', 'scope_id'])
    op.create_index('ix_alert_rules_enabled', 'alert_rules', ['enabled'])
    op.add_column('alerts', sa.Column('rule_ref', sa.String(length=32), nullable=True))
    op.create_index('ix_alerts_rule_ref', 'alerts', ['rule_ref'])


def downgrade() -> None:
    op.drop_index('ix_alerts_rule_ref', table_name='alerts')
    op.drop_column('alerts', 'rule_ref')
    op.drop_index('ix_alert_rules_enabled', table_name='alert_rules')
    op.drop_index('ix_alert_rules_scope', table_name='alert_rules')
    op.drop_table('alert_rules')
