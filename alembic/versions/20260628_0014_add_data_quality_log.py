"""add_data_quality_log

Per-gap ledger for the data-quality framework: one row per detected gap
(missing/stale data), resolved when the gap is later filled.

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa

revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'data_quality_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('stock_id', sa.Integer(), nullable=True),     # null = date/global gap
        sa.Column('table_name', sa.String(40), nullable=False),
        sa.Column('gap_type', sa.String(40), nullable=False),   # missing_ohlcv, stale_fundamentals, ...
        sa.Column('gap_detail', sa.Text(), nullable=True),
        sa.Column('detected_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['stock_id'], ['stocks.id'], ondelete='CASCADE'),
    )
    # one OPEN gap per (stock, table, gap_type) — re-detection updates the same row.
    op.create_index('uq_data_quality_open', 'data_quality_log',
                    ['stock_id', 'table_name', 'gap_type'],
                    unique=True, postgresql_where=sa.text('resolved_at IS NULL'))
    op.create_index('ix_data_quality_unresolved', 'data_quality_log',
                    ['resolved_at', 'detected_at'])


def downgrade():
    op.drop_index('ix_data_quality_unresolved', table_name='data_quality_log')
    op.drop_index('uq_data_quality_open', table_name='data_quality_log')
    op.drop_table('data_quality_log')
