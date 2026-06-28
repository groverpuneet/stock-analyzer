"""add_watchlist_changes

Tracks newly-added watchlist stocks detected by the Dagster watchlist_change_sensor,
so each new stock is backfilled/processed exactly once.

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'watchlist_changes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('stock_id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(40), nullable=True),
        sa.Column('watchlist_name', sa.String(60), nullable=False, server_default='Default'),
        sa.Column('detected_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('handled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('handled_at', sa.DateTime(), nullable=True),
        sa.Column('run_ids', sa.Text(), nullable=True),   # comma-separated Dagster run ids triggered
        sa.Column('notes', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['stock_id'], ['stocks.id'], ondelete='CASCADE'),
        # one detection record per stock per watchlist — a stock is processed once
        sa.UniqueConstraint('stock_id', 'watchlist_name', name='uq_watchlist_change_stock'),
    )
    op.create_index('ix_watchlist_changes_unhandled', 'watchlist_changes',
                    ['handled', 'watchlist_name'])


def downgrade():
    op.drop_index('ix_watchlist_changes_unhandled', table_name='watchlist_changes')
    op.drop_table('watchlist_changes')
