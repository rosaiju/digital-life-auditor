"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-09-24 20:28:12.809136

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the initial schema. plaid_items.access_token holds Fernet ciphertext (see app.models.types)."""
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('hashed_password', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_table('insights',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('content', sa.JSON(), nullable=False),
    sa.Column('generated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_insights_id'), 'insights', ['id'], unique=False)
    op.create_index(op.f('ix_insights_user_id'), 'insights', ['user_id'], unique=False)
    op.create_table('plaid_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('access_token', sa.String(), nullable=False),
    sa.Column('item_id', sa.String(), nullable=False),
    sa.Column('institution_name', sa.String(), nullable=True),
    sa.Column('cursor', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('item_id')
    )
    op.create_index(op.f('ix_plaid_items_id'), 'plaid_items', ['id'], unique=False)
    op.create_index(op.f('ix_plaid_items_user_id'), 'plaid_items', ['user_id'], unique=False)
    op.create_table('subscriptions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('merchant_name', sa.String(), nullable=False),
    sa.Column('display_name', sa.String(), nullable=True),
    sa.Column('amount', sa.Float(), nullable=False),
    sa.Column('frequency', sa.String(), nullable=False),
    sa.Column('category', sa.String(), nullable=True),
    sa.Column('last_charge_date', sa.Date(), nullable=True),
    sa.Column('next_charge_date', sa.Date(), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('cancel_url', sa.String(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'merchant_name', name='uq_subscription_user_merchant')
    )
    op.create_index(op.f('ix_subscriptions_id'), 'subscriptions', ['id'], unique=False)
    op.create_index(op.f('ix_subscriptions_user_id'), 'subscriptions', ['user_id'], unique=False)
    op.create_table('transactions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('plaid_transaction_id', sa.String(), nullable=False),
    sa.Column('merchant_name', sa.String(), nullable=True),
    sa.Column('amount', sa.Float(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('category', sa.String(), nullable=True),
    sa.Column('raw_json', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('plaid_transaction_id')
    )
    op.create_index(op.f('ix_transactions_id'), 'transactions', ['id'], unique=False)
    op.create_index('ix_transactions_user_date', 'transactions', ['user_id', 'date'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_transactions_user_date', table_name='transactions')
    op.drop_index(op.f('ix_transactions_id'), table_name='transactions')
    op.drop_table('transactions')
    op.drop_index(op.f('ix_subscriptions_user_id'), table_name='subscriptions')
    op.drop_index(op.f('ix_subscriptions_id'), table_name='subscriptions')
    op.drop_table('subscriptions')
    op.drop_index(op.f('ix_plaid_items_user_id'), table_name='plaid_items')
    op.drop_index(op.f('ix_plaid_items_id'), table_name='plaid_items')
    op.drop_table('plaid_items')
    op.drop_index(op.f('ix_insights_user_id'), table_name='insights')
    op.drop_index(op.f('ix_insights_id'), table_name='insights')
    op.drop_table('insights')
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
