"""add_completeness_score

Per-stock 0-100 data-completeness score on stock_scores (price, indicators,
fundamentals, news, shareholding, signals each contribute).

Revision ID: 0016
Revises: 0015
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa

revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('stock_scores', sa.Column('data_completeness_score', sa.Numeric(), nullable=True))


def downgrade():
    op.drop_column('stock_scores', 'data_completeness_score')
