"""add_concall_transcripts

Earnings-call transcript links + (on-demand) FinBERT sentiment / Claude summary.

Revision ID: 0018
Revises: 0017
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa

revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'concall_transcripts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('stock_id', sa.Integer(), nullable=False),
        sa.Column('quarter', sa.String(16), nullable=True),
        sa.Column('transcript_url', sa.Text(), nullable=True),
        sa.Column('transcript_text', sa.Text(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('sentiment_score', sa.Numeric(), nullable=True),
        sa.Column('key_themes', sa.Text(), nullable=True),
        sa.Column('source', sa.String(20), nullable=False, server_default='screener'),
        sa.Column('published_at', sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['stock_id'], ['stocks.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('stock_id', 'quarter', name='uq_concall_stock_quarter'),
    )


def downgrade():
    op.drop_table('concall_transcripts')
