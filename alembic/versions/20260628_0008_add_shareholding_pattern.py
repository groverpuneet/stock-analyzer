"""Add shareholding_pattern table for quarterly promoter/FII/DII/public holdings.
Revision ID: 0008
Revises: 0007
Create Date: 2026-06-28
"""
from alembic import op

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS shareholding_pattern (
            id              SERIAL PRIMARY KEY,
            stock_id        INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
            symbol          VARCHAR(30) NOT NULL,
            quarter_end     DATE NOT NULL,
            promoter_pct    DECIMAL(5,2),
            fii_pct         DECIMAL(5,2),
            dii_pct         DECIMAL(5,2),
            government_pct  DECIMAL(5,2),
            public_pct      DECIMAL(5,2),
            num_shareholders INTEGER,
            source          VARCHAR(30) DEFAULT 'screener',
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(stock_id, quarter_end)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_shp_symbol ON shareholding_pattern(symbol)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_shp_quarter ON shareholding_pattern(quarter_end)")
    op.execute("""
        INSERT INTO data_refresh_log (source, tier, status, rows_upserted)
        VALUES ('shareholding_pattern', 'weekly', 'never_run', 0)
        ON CONFLICT (source) DO NOTHING
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS shareholding_pattern")
    op.execute("DELETE FROM data_refresh_log WHERE source = 'shareholding_pattern'")
