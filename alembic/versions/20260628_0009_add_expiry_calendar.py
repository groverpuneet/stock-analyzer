"""add_expiry_calendar

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'expiry_calendar',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('expiry_date', sa.Date(), nullable=False),
        sa.Column('expiry_type', sa.String(10), nullable=False),   # weekly / monthly / quarterly
        sa.Column('segment', sa.String(10), nullable=False, server_default='NFO'),
        sa.Column('symbol_count', sa.Integer(), nullable=False),
        sa.Column('has_futures', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('source', sa.String(20), nullable=False, server_default='kite_nfo'),
        sa.Column('fetched_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('expiry_date', name='uq_expiry_calendar_date'),
    )


def downgrade():
    op.drop_table('expiry_calendar')
