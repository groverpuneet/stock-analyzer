"""add_pe_percentile

Adds pe_percentile to stock_scores: where the stock's current P/E sits within
its own ~5yr historical P/E range (0 = cheapest ever, 100 = most expensive).

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('stock_scores', sa.Column('pe_percentile', sa.Numeric(), nullable=True))


def downgrade():
    op.drop_column('stock_scores', 'pe_percentile')
