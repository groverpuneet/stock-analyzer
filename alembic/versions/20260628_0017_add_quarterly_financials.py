"""add_quarterly_financials

Quarterly financials (P&L + balance sheet + cash flow) per stock from Screener.in.
Also adds a (stock_id, period_end) unique key to earnings_calendar so historical
quarterly results (which often lack a results_date) upsert cleanly.

Revision ID: 0017
Revises: 0016
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa

revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'quarterly_financials',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('stock_id', sa.Integer(), nullable=False),
        sa.Column('quarter', sa.String(16), nullable=True),     # e.g. 'Mar 2026'
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('revenue', sa.Numeric(), nullable=True),
        sa.Column('ebitda', sa.Numeric(), nullable=True),
        sa.Column('pat', sa.Numeric(), nullable=True),
        sa.Column('eps', sa.Numeric(), nullable=True),
        sa.Column('debt', sa.Numeric(), nullable=True),
        sa.Column('cash', sa.Numeric(), nullable=True),
        sa.Column('ocf', sa.Numeric(), nullable=True),
        sa.Column('capex', sa.Numeric(), nullable=True),
        sa.Column('source', sa.String(20), nullable=False, server_default='screener'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['stock_id'], ['stocks.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('stock_id', 'period_end', name='uq_quarterly_financials'),
    )
    op.create_unique_constraint('uq_earnings_period', 'earnings_calendar', ['stock_id', 'period_end'])


def downgrade():
    op.drop_constraint('uq_earnings_period', 'earnings_calendar', type_='unique')
    op.drop_table('quarterly_financials')
