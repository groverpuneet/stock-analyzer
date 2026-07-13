"""Survivorship security-master columns — backtest Phase 0b.

Adds listing_date/delisting_date/is_active to stocks so a point-in-time
backtest can exclude stocks that hadn't listed yet or had already delisted
as of a given `as_of` date.

v1 scope (deliberately conservative — see survivorship_collector.py docstring):
only positive evidence sets is_active=TRUE + listing_date, sourced from NSE's
official current mainboard list (EQUITY_L.csv). Nothing is flipped to FALSE
by this migration/collector — `stocks` is a broad historical symbol master
(~10.7k rows: mainboard + SME + legacy) while EQUITY_L.csv only covers
~2.4k current mainboard names, so "absent from EQUITY_L.csv" is NOT reliable
evidence of delisting (could just be SME-listed, an ETF, or non-NSE). True
delisted-name identification (needed to fully remove survivorship bias) is
deferred to a historical index-membership backfill.

Revision ID: 0027
Revises: 0026
Create Date: 2026-07-12
"""
from alembic import op

revision = '0027'
down_revision = '0026'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE stocks
            ADD COLUMN IF NOT EXISTS listing_date DATE,
            ADD COLUMN IF NOT EXISTS delisting_date DATE,
            ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_stocks_is_active ON stocks (is_active)")
    op.execute("""INSERT INTO data_refresh_log (source, tier, status, rows_upserted)
                  VALUES ('survivorship_master', 'weekly', 'never_run', 0)
                  ON CONFLICT (source) DO NOTHING""")


def downgrade():
    op.execute("ALTER TABLE stocks DROP COLUMN IF EXISTS listing_date")
    op.execute("ALTER TABLE stocks DROP COLUMN IF EXISTS delisting_date")
    op.execute("ALTER TABLE stocks DROP COLUMN IF EXISTS is_active")
    op.execute("DELETE FROM data_refresh_log WHERE source='survivorship_master'")
