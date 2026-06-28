"""Add fno_data table for F&O participant OI and India VIX.
Revision ID: 0007
Revises: 0006
Create Date: 2026-06-27
"""
from alembic import op

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS fno_data (
            id                  SERIAL PRIMARY KEY,
            date                DATE NOT NULL UNIQUE,
            india_vix           DECIMAL(6,2),
            -- Aggregate index options (NIFTY + BANKNIFTY + all index options)
            index_call_oi       BIGINT,
            index_put_oi        BIGINT,
            index_pcr           DECIMAL(6,3),
            -- Aggregate stock options
            stock_call_oi       BIGINT,
            stock_put_oi        BIGINT,
            stock_pcr           DECIMAL(6,3),
            -- Total market (index + stock)
            total_call_oi       BIGINT,
            total_put_oi        BIGINT,
            total_pcr           DECIMAL(6,3),
            -- FII positioning in index options (key sentiment signal)
            fii_index_call_oi   BIGINT,
            fii_index_put_oi    BIGINT,
            fii_index_pcr       DECIMAL(6,3),
            -- FII futures positioning
            fii_fut_index_long  BIGINT,
            fii_fut_index_short BIGINT,
            -- DII index options
            dii_index_call_oi   BIGINT,
            dii_index_put_oi    BIGINT,
            dii_index_pcr       DECIMAL(6,3),
            -- Max pain (NULL until per-strike data available via browser automation)
            max_pain            DECIMAL(10,2),
            created_at          TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("""
        INSERT INTO data_refresh_log (source, tier, status, rows_upserted)
        VALUES ('fno_data', 'daily', 'never_run', 0)
        ON CONFLICT (source) DO NOTHING
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS fno_data")
    op.execute("DELETE FROM data_refresh_log WHERE source = 'fno_data'")
