"""track per-bank sync health

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-25 09:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('plaid_items', sa.Column('status', sa.String(), server_default='ok', nullable=False))
    op.add_column('plaid_items', sa.Column('last_synced_at', sa.DateTime(), nullable=True))
    op.add_column('plaid_items', sa.Column('last_error', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('plaid_items', 'last_error')
    op.drop_column('plaid_items', 'last_synced_at')
    op.drop_column('plaid_items', 'status')
