"""Add institutional_holdings_13f, tracked_filers, congress_trades, mf_stock_holdings tables.

Revision ID: 0021
Revises: 0020
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0021'
down_revision = '0020'
branch_labels = None
depends_on = None

# Top 20 institutional filers to track
TOP_FILERS = [
    ('Berkshire Hathaway', '0001067983', 'VALUE'),
    ('Bridgewater Associates', '0001350694', 'HEDGE'),
    ('Renaissance Technologies', '0001037389', 'QUANT'),
    ('Two Sigma', '0001450144', 'QUANT'),
    ('Citadel Advisors', '0001423053', 'HEDGE'),
    ('D.E. Shaw', '0001009207', 'QUANT'),
    ('Pershing Square', '0001336528', 'ACTIVIST'),
    ('Third Point', '0001040273', 'ACTIVIST'),
    ('Elliott Management', '0001048445', 'ACTIVIST'),
    ('Viking Global', '0001103804', 'HEDGE'),
    ('Tiger Global', '0001167483', 'HEDGE'),
    ('Lone Pine Capital', '0001061165', 'HEDGE'),
    ('Coatue Management', '0001535392', 'HEDGE'),
    ('Baupost Group', '0001061768', 'VALUE'),
    ('Greenlight Capital', '0001079114', 'VALUE'),
    ('Appaloosa Management', '0001138995', 'HEDGE'),
    ('Icahn Enterprises', '0000051412', 'ACTIVIST'),
    ('Druckenmiller Family Office', '0001536411', 'MACRO'),
    ('Soros Fund Management', '0001029160', 'MACRO'),
    ('Point72', '0001603466', 'HEDGE'),
]


def upgrade():
    # tracked_filers — institutional investors we track via 13F
    op.create_table(
        'tracked_filers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('filer_name', sa.String(200), nullable=False, unique=True),
        sa.Column('filer_cik', sa.String(20), nullable=False, unique=True),
        sa.Column('category', sa.String(20)),  # VALUE / HEDGE / QUANT / ACTIVIST / MACRO
        sa.Column('aum_usd', sa.BigInteger()),  # Approximate AUM in USD
        sa.Column('active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # Seed top filers
    for name, cik, category in TOP_FILERS:
        op.execute(f"""
            INSERT INTO tracked_filers (filer_name, filer_cik, category, active)
            VALUES ('{name}', '{cik}', '{category}', true)
            ON CONFLICT (filer_cik) DO NOTHING
        """)

    # institutional_holdings_13f — quarterly 13F holdings data
    op.create_table(
        'institutional_holdings_13f',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('filer_id', sa.Integer(), sa.ForeignKey('tracked_filers.id', ondelete='CASCADE')),
        sa.Column('filer_cik', sa.String(20), nullable=False),
        sa.Column('quarter', sa.String(10), nullable=False),  # e.g. '2026Q1'
        sa.Column('symbol', sa.String(20)),
        sa.Column('cusip', sa.String(20)),
        sa.Column('issuer_name', sa.String(200)),
        sa.Column('title_of_class', sa.String(50)),
        sa.Column('shares_held', sa.BigInteger()),
        sa.Column('market_value_usd', sa.BigInteger()),
        sa.Column('pct_of_portfolio', sa.Numeric(8, 4)),
        sa.Column('qoq_change_shares', sa.BigInteger()),
        sa.Column('qoq_change_pct', sa.Numeric(8, 2)),
        sa.Column('filing_date', sa.Date()),
        sa.Column('source', sa.String(50)),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('filer_cik', 'quarter', 'cusip', name='holdings_13f_filer_quarter_cusip_key'),
    )
    op.create_index('ix_holdings_13f_filer_cik', 'institutional_holdings_13f', ['filer_cik'])
    op.create_index('ix_holdings_13f_quarter', 'institutional_holdings_13f', ['quarter'])
    op.create_index('ix_holdings_13f_symbol', 'institutional_holdings_13f', ['symbol'])

    # congress_trades — US politician stock trades (pending data source)
    op.create_table(
        'congress_trades',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('symbol', sa.String(20)),
        sa.Column('politician', sa.String(200), nullable=False),
        sa.Column('party', sa.String(20)),  # D / R / I
        sa.Column('chamber', sa.String(20)),  # House / Senate
        sa.Column('state', sa.String(10)),
        sa.Column('transaction_type', sa.String(20)),  # BUY / SELL / EXCHANGE
        sa.Column('amount_min', sa.BigInteger()),
        sa.Column('amount_max', sa.BigInteger()),
        sa.Column('trade_date', sa.Date()),
        sa.Column('disclosure_date', sa.Date()),
        sa.Column('days_to_disclose', sa.Integer()),
        sa.Column('description', sa.String(500)),
        sa.Column('source', sa.String(50)),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_congress_trades_symbol', 'congress_trades', ['symbol'])
    op.create_index('ix_congress_trades_politician', 'congress_trades', ['politician'])
    op.create_index('ix_congress_trades_trade_date', 'congress_trades', ['trade_date'])

    # mf_stock_holdings — Indian MF holdings per stock
    op.create_table(
        'mf_stock_holdings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('stock_id', sa.Integer(), sa.ForeignKey('stocks.id', ondelete='CASCADE')),
        sa.Column('month', sa.Date(), nullable=False),  # First of month
        sa.Column('total_mf_schemes', sa.Integer()),
        sa.Column('total_units', sa.BigInteger()),
        sa.Column('total_market_value_cr', sa.Numeric(14, 2)),
        sa.Column('ownership_pct', sa.Numeric(6, 2)),
        sa.Column('mom_change_pct', sa.Numeric(6, 2)),
        sa.Column('top_holders', JSONB),  # Top 5 MFs holding the stock
        sa.Column('source', sa.String(50)),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('stock_id', 'month', name='mf_stock_holdings_stock_month_key'),
    )
    op.create_index('ix_mf_stock_holdings_stock_id', 'mf_stock_holdings', ['stock_id'])
    op.create_index('ix_mf_stock_holdings_month', 'mf_stock_holdings', ['month'])

    # Add refresh_log entries
    op.execute("""
        INSERT INTO data_refresh_log (source, tier, status, rows_upserted)
        VALUES
            ('sec_13f', 'tier3', 'pending', 0),
            ('congress_trades', 'tier3', 'pending', 0),
            ('mf_stock_holdings', 'tier2', 'pending', 0)
        ON CONFLICT DO NOTHING
    """)


def downgrade():
    op.drop_table('mf_stock_holdings')
    op.drop_table('congress_trades')
    op.drop_table('institutional_holdings_13f')
    op.drop_table('tracked_filers')
    op.execute("DELETE FROM data_refresh_log WHERE source IN ('sec_13f', 'congress_trades', 'mf_stock_holdings')")
