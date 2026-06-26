"""Add stock_scores and indicator_baselines tables for monthly model refresh.
Revision ID: 0006
Revises: 0005
Create Date: 2026-06-26
"""
from alembic import op

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS stock_scores (
            id              SERIAL PRIMARY KEY,
            stock_id        INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
            date            DATE NOT NULL,
            rsi_rank        DECIMAL(5,2),
            momentum_score  DECIMAL(5,2),
            volume_rank     DECIMAL(5,2),
            macd_rank       DECIMAL(5,2),
            composite_score DECIMAL(5,2),
            UNIQUE(stock_id, date)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS indicator_baselines (
            id            SERIAL PRIMARY KEY,
            stock_id      INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
            computed_date DATE NOT NULL,
            indicator     VARCHAR(30) NOT NULL,
            mean_val      DECIMAL(12,4),
            std_val       DECIMAL(12,4),
            p10           DECIMAL(12,4),
            p25           DECIMAL(12,4),
            p75           DECIMAL(12,4),
            p90           DECIMAL(12,4),
            UNIQUE(stock_id, computed_date, indicator)
        )
    """)
    op.execute("""
        INSERT INTO data_refresh_log (source, tier, status)
        VALUES ('model_refresh', 'monthly', 'never_run')
        ON CONFLICT (source) DO NOTHING
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS stock_scores CASCADE")
    op.execute("DROP TABLE IF EXISTS indicator_baselines CASCADE")
    op.execute("DELETE FROM data_refresh_log WHERE source = 'model_refresh'")
