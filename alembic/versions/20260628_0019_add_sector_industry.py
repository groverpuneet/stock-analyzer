"""add_sector_industry

sector + industry on stocks (populated from Screener.in).

Revision ID: 0019
Revises: 0018
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa

revision = '0019'
down_revision = '0018'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('stocks', sa.Column('sector', sa.String(80), nullable=True))
    op.add_column('stocks', sa.Column('industry', sa.String(120), nullable=True))


def downgrade():
    op.drop_column('stocks', 'industry')
    op.drop_column('stocks', 'sector')
