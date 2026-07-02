"""Add volume indicators to technical_indicators + volume_signal to stock_scores.

Volume as an indicator (Session K):
  technical_indicators gains: volume_sma_20, volume_ratio, volume_trend, obv, vwap
  stock_scores gains: volume_signal (VOLUME_BREAKOUT / VOLUME_BREAKDOWN / LOW_VOLUME_MOVE)

Revision ID: 0022
Revises: 0021
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa

revision = '0022'
down_revision = '0021'
branch_labels = None
depends_on = None


def upgrade():
    # Volume-derived indicators, computed daily alongside RSI/MACD/etc.
    op.add_column('technical_indicators', sa.Column('volume_sma_20', sa.Numeric(20, 2)))
    op.add_column('technical_indicators', sa.Column('volume_ratio', sa.Numeric(10, 4)))
    op.add_column('technical_indicators', sa.Column('volume_trend', sa.String(10)))  # RISING / FALLING / FLAT
    op.add_column('technical_indicators', sa.Column('obv', sa.BigInteger()))
    op.add_column('technical_indicators', sa.Column('vwap', sa.Numeric(20, 4)))

    # Daily volume signal (price move confirmed / contradicted by volume)
    op.add_column('stock_scores', sa.Column('volume_signal', sa.String(20)))


def downgrade():
    op.drop_column('stock_scores', 'volume_signal')
    op.drop_column('technical_indicators', 'vwap')
    op.drop_column('technical_indicators', 'obv')
    op.drop_column('technical_indicators', 'volume_trend')
    op.drop_column('technical_indicators', 'volume_ratio')
    op.drop_column('technical_indicators', 'volume_sma_20')
