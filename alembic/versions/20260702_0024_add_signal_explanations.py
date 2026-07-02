"""4-pillar signal engine — per-stock, per-horizon explainable signals.

signal_explanations stores, for each (stock_id, date, horizon), the four pillar scores
(technical / fundamental / flow / external) with plain-English reasoning arrays, the
combined overall signal, confidence, and metadata (contrary indicators, what-would-change,
cached external sentiment). advisor_opinions is a Pillar-5 placeholder (weight 0 for now).

Revision ID: 0024
Revises: 0023
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0024'
down_revision = '0023'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'signal_explanations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('stock_id', sa.Integer(), sa.ForeignKey('stocks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('horizon', sa.String(10), nullable=False),  # SHORT / MID / LONG
        sa.Column('signal_type', sa.String(20)),              # STRONG_BUY..STRONG_SELL
        sa.Column('strength', sa.String(20)),
        sa.Column('confidence', sa.String(10)),               # LOW / MEDIUM / HIGH
        sa.Column('all_pillars_agree', sa.Boolean(), default=False),
        sa.Column('technical_score', sa.Numeric(6, 2)),
        sa.Column('technical_reasoning', JSONB),
        sa.Column('fundamental_score', sa.Numeric(6, 2)),
        sa.Column('fundamental_reasoning', JSONB),
        sa.Column('flow_score', sa.Numeric(6, 2)),
        sa.Column('flow_reasoning', JSONB),
        sa.Column('external_score', sa.Numeric(6, 2)),
        sa.Column('external_reasoning', JSONB),
        sa.Column('advisor_score', sa.Numeric(6, 2)),
        sa.Column('advisor_reasoning', JSONB),
        sa.Column('overall_score', sa.Numeric(6, 2)),
        sa.Column('overall_reasoning', JSONB),
        sa.Column('key_metrics', JSONB),
        sa.Column('contrary_indicators', JSONB),
        sa.Column('what_would_change', JSONB),
        sa.Column('cached_external_sentiment', JSONB),
        sa.Column('external_cache_expiry', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('stock_id', 'date', 'horizon', name='signal_explanations_stock_date_horizon_key'),
    )
    op.create_index('ix_signal_explanations_stock', 'signal_explanations', ['stock_id'])
    op.create_index('ix_signal_explanations_date', 'signal_explanations', ['date'])
    op.create_index('ix_signal_explanations_horizon', 'signal_explanations', ['horizon'])

    # Pillar 5 placeholder — trusted advisor opinions (weight 0 until populated).
    op.create_table(
        'advisor_opinions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('advisor_name', sa.String(200), nullable=False),
        sa.Column('advisor_type', sa.String(30)),  # SEBI_RIA / TWITTER_ANALYST / YOUTUBE_CHANNEL / NEWSLETTER
        sa.Column('stock_id', sa.Integer(), sa.ForeignKey('stocks.id', ondelete='CASCADE')),
        sa.Column('opinion', sa.String(20)),       # BUY / SELL / HOLD
        sa.Column('target_price', sa.Numeric(14, 2)),
        sa.Column('time_horizon', sa.String(10)),
        sa.Column('published_date', sa.Date()),
        sa.Column('source_url', sa.String(500)),
        sa.Column('sentiment_score', sa.Numeric(6, 2)),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_advisor_opinions_stock', 'advisor_opinions', ['stock_id'])


def downgrade():
    op.drop_table('advisor_opinions')
    op.drop_table('signal_explanations')
