"""loop detection: execution flag + span call signatures (ADR-0014)

Looping executions are flagged, not failed: a stuck agent can repeat itself
forever without any span erroring. The SDK exports salted, run-scoped call
signatures; the backend re-derives repeats and cycles from them on ingest.

Revision ID: b7c1e5a9d3f2
Revises: e2f5a9c3b7d1
Create Date: 2026-10-17
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = 'b7c1e5a9d3f2'
down_revision = 'e2f5a9c3b7d1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'executions',
        sa.Column(
            'loop_detected',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        'executions',
        sa.Column('loop_info', JSONB(), nullable=True),
    )
    op.create_index(
        'ix_executions_loop_detected', 'executions', ['loop_detected']
    )
    op.add_column(
        'spans',
        sa.Column('call_sig', sa.String(length=24), nullable=True),
    )
    op.create_index(
        'ix_spans_execution_call_sig', 'spans', ['execution_id', 'call_sig']
    )


def downgrade() -> None:
    op.drop_index('ix_spans_execution_call_sig', table_name='spans')
    op.drop_column('spans', 'call_sig')
    op.drop_index('ix_executions_loop_detected', table_name='executions')
    op.drop_column('executions', 'loop_info')
    op.drop_column('executions', 'loop_detected')
