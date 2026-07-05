"""Adjustment factors — corp-action-adjusted price series for backtesting.

Backtest Phase 0a. Stores per-event price adjustment factors (splits/bonus now,
dividends later) so a point-in-time provider can build an adjusted close:
    adj_close(t) = raw_close(t) * PROD(price_factor for events with ex_date > t)

Source note: `corporate_actions` is a rolling forward ±90-day announcement window,
NOT a historical archive — so historical splits come from yfinance's `.splits`
(the same lib full_history_backfill.py already uses). yfinance folds bonus issues
into the split ratio, so one pull covers splits + bonus. The table can also ingest
forward split/bonus events from `corporate_actions` later.

Revision ID: 0026
Revises: 0025
Create Date: 2026-07-05
"""
from alembic import op

revision = '0026'
down_revision = '0025'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS adjustment_factors (
            id           SERIAL PRIMARY KEY,
            stock_id     INTEGER NOT NULL REFERENCES stocks(id),
            ex_date      DATE NOT NULL,
            event_type   VARCHAR(10) NOT NULL,      -- split / bonus / dividend
            ratio        VARCHAR(20),               -- human-readable ("2", "1.3333", "Rs 5")
            price_factor DECIMAL(18,10) NOT NULL,   -- multiply prices with date < ex_date
            source       VARCHAR(20) NOT NULL DEFAULT 'yfinance',
            created_at   TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT uq_adjustment_factors UNIQUE (stock_id, ex_date, event_type, source)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_adjustment_factors_stock "
               "ON adjustment_factors (stock_id, ex_date)")
    op.execute("""INSERT INTO data_refresh_log (source, tier, status, rows_upserted)
                  VALUES ('adjustment_factors', 'weekly', 'never_run', 0)
                  ON CONFLICT (source) DO NOTHING""")


def downgrade():
    op.execute("DROP TABLE IF EXISTS adjustment_factors")
    op.execute("DELETE FROM data_refresh_log WHERE source='adjustment_factors'")
