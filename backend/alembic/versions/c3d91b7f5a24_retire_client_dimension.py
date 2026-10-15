"""retire the client attribution dimension (ADR-0011)

Destructive: the client dimension has no registry, no membership and no scope,
and it overlapped project on every surface. Dropping it removes the table, both
FK columns, and the retained analytics rows for the dimension; historical
attribution is not migrated.

Revision ID: c3d91b7f5a24
Revises: a2f7c1d94b3e
Create Date: 2026-10-15
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'c3d91b7f5a24'
down_revision = 'a2f7c1d94b3e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index(op.f('ix_executions_client_id'), table_name='executions')
    op.drop_constraint('executions_client_id_fkey', 'executions', type_='foreignkey')
    op.drop_column('executions', 'client_id')

    op.drop_index(op.f('ix_budgets_client_id'), table_name='budgets')
    op.drop_constraint('budgets_client_id_fkey', 'budgets', type_='foreignkey')
    op.drop_column('budgets', 'client_id')

    # Dimension rows keyed on the retired dimension.
    op.execute("DELETE FROM daily_metrics WHERE dimension = 'client'")

    op.drop_index(op.f('ix_clients_external_key'), table_name='clients')
    op.drop_table('clients')


def downgrade() -> None:
    # Recreates the empty schema: the dimension's data is not recoverable.
    op.create_table(
        'clients',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('external_key', sa.String(length=120), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=True),
        sa.Column('first_seen', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_clients_external_key'), 'clients', ['external_key'], unique=True
    )

    op.add_column('executions', sa.Column('client_id', sa.String(length=32), nullable=True))
    op.create_index(
        op.f('ix_executions_client_id'), 'executions', ['client_id'], unique=False
    )
    op.create_foreign_key(
        'executions_client_id_fkey', 'executions', 'clients', ['client_id'], ['id']
    )

    op.add_column('budgets', sa.Column('client_id', sa.String(length=32), nullable=True))
    op.create_index(op.f('ix_budgets_client_id'), 'budgets', ['client_id'], unique=False)
    op.create_foreign_key(
        'budgets_client_id_fkey', 'budgets', 'clients', ['client_id'], ['id']
    )
