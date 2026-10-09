"""budget department/team scope

Revision ID: b3f1c8a97d2e
Revises: f8a2c4d61e07
Create Date: 2026-10-09
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'b3f1c8a97d2e'
down_revision = 'f8a2c4d61e07'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'budgets',
        sa.Column('department_id', sa.String(length=32), nullable=True),
    )
    op.add_column(
        'budgets',
        sa.Column('team_id', sa.String(length=32), nullable=True),
    )
    op.create_foreign_key(
        'fk_budgets_department_id', 'budgets', 'departments', ['department_id'], ['id']
    )
    op.create_foreign_key('fk_budgets_team_id', 'budgets', 'teams', ['team_id'], ['id'])
    op.create_index('ix_budgets_department_id', 'budgets', ['department_id'])
    op.create_index('ix_budgets_team_id', 'budgets', ['team_id'])


def downgrade() -> None:
    op.drop_index('ix_budgets_team_id', table_name='budgets')
    op.drop_index('ix_budgets_department_id', table_name='budgets')
    op.drop_constraint('fk_budgets_team_id', 'budgets', type_='foreignkey')
    op.drop_constraint('fk_budgets_department_id', 'budgets', type_='foreignkey')
    op.drop_column('budgets', 'team_id')
    op.drop_column('budgets', 'department_id')
