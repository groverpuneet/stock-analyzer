"""Add analyst_targets, pledging_alerts, sast_disclosures tables.

Revision ID: 0020
Revises: 0019
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa

revision = '0020'
down_revision = '0019'
branch_labels = None
depends_on = None


def upgrade():
    # analyst_targets — analyst consensus ratings and price targets
    op.create_table(
        'analyst_targets',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('stock_id', sa.Integer(), sa.ForeignKey('stocks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('analyst_count', sa.Integer()),
        sa.Column('buy_count', sa.Integer()),
        sa.Column('hold_count', sa.Integer()),
        sa.Column('sell_count', sa.Integer()),
        sa.Column('avg_target_price', sa.Numeric(12, 2)),
        sa.Column('high_target', sa.Numeric(12, 2)),
        sa.Column('low_target', sa.Numeric(12, 2)),
        sa.Column('current_price', sa.Numeric(12, 2)),
        sa.Column('upside_pct', sa.Numeric(8, 2)),
        sa.Column('consensus_rating', sa.String(20)),  # STRONG_BUY / BUY / HOLD / SELL / STRONG_SELL
        sa.Column('source', sa.String(50)),
        sa.Column('scraped_at', sa.DateTime()),
        sa.UniqueConstraint('stock_id', 'date', name='analyst_targets_stock_date_key'),
    )
    op.create_index('ix_analyst_targets_stock_id', 'analyst_targets', ['stock_id'])
    op.create_index('ix_analyst_targets_date', 'analyst_targets', ['date'])

    # pledging_alerts — promoter pledging changes and alerts
    op.create_table(
        'pledging_alerts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('stock_id', sa.Integer(), sa.ForeignKey('stocks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('current_pledge_pct', sa.Numeric(6, 2)),
        sa.Column('previous_pledge_pct', sa.Numeric(6, 2)),
        sa.Column('change_pct', sa.Numeric(6, 2)),
        sa.Column('alert_type', sa.String(20)),  # RISING_PLEDGE / FALLING_PLEDGE / HIGH_PLEDGE
        sa.Column('severity', sa.String(10)),    # LOW / MEDIUM / HIGH / CRITICAL
        sa.Column('resolved', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('stock_id', 'date', 'alert_type', name='pledging_alerts_stock_date_type_key'),
    )
    op.create_index('ix_pledging_alerts_stock_id', 'pledging_alerts', ['stock_id'])
    op.create_index('ix_pledging_alerts_date', 'pledging_alerts', ['date'])
    op.create_index('ix_pledging_alerts_severity', 'pledging_alerts', ['severity'])

    # sast_disclosures — Substantial Acquisition of Shares and Takeovers
    op.create_table(
        'sast_disclosures',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('stock_id', sa.Integer(), sa.ForeignKey('stocks.id', ondelete='CASCADE')),
        sa.Column('symbol', sa.String(50)),  # for stocks not in our universe
        sa.Column('acquirer_name', sa.String(200), nullable=False),
        sa.Column('acquirer_type', sa.String(20)),  # PROMOTER / FII / DII / INDIVIDUAL / COMPANY
        sa.Column('shares_acquired', sa.BigInteger()),
        sa.Column('pct_acquired', sa.Numeric(8, 4)),
        sa.Column('total_holding_pct', sa.Numeric(8, 4)),
        sa.Column('acquisition_date', sa.Date()),
        sa.Column('disclosure_date', sa.Date(), nullable=False),
        sa.Column('transaction_type', sa.String(50)),  # ACQUISITION / DISPOSAL / OPEN_OFFER / etc
        sa.Column('source', sa.String(50)),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_sast_disclosures_stock_id', 'sast_disclosures', ['stock_id'])
    op.create_index('ix_sast_disclosures_disclosure_date', 'sast_disclosures', ['disclosure_date'])
    op.create_index('ix_sast_disclosures_acquirer_name', 'sast_disclosures', ['acquirer_name'])

    # Add refresh_log entries for new sources
    op.execute("""
        INSERT INTO data_refresh_log (source, tier, status, rows_upserted)
        VALUES
            ('analyst_targets', 'tier1', 'pending', 0),
            ('pledging_alerts', 'tier1', 'pending', 0),
            ('sast_disclosures', 'tier1', 'pending', 0)
        ON CONFLICT DO NOTHING
    """)


def downgrade():
    op.drop_table('sast_disclosures')
    op.drop_table('pledging_alerts')
    op.drop_table('analyst_targets')
    op.execute("DELETE FROM data_refresh_log WHERE source IN ('analyst_targets', 'pledging_alerts', 'sast_disclosures')")
