"""Portfolio schema — private, localhost-only holdings with encrypted sensitive columns.

Separate `portfolio` schema (isolated from the public market-data tables). Sensitive
columns (quantity, buying_price, target_price, stop_loss) are stored as BYTEA and
encrypted at rest with pgcrypto's pgp_sym_encrypt — the key lives only in .env
(PORTFOLIO_ENCRYPTION_KEY), never in the database. P&L / current value are NEVER stored;
always computed at query time from daily_prices.

Revision ID: 0023
Revises: 0022
Create Date: 2026-07-02
"""
from alembic import op

revision = '0023'
down_revision = '0022'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE SCHEMA IF NOT EXISTS portfolio")

    # holdings — sensitive numeric fields are BYTEA (pgp_sym_encrypt ciphertext)
    op.execute("""
        CREATE TABLE IF NOT EXISTS portfolio.holdings (
            id            SERIAL PRIMARY KEY,
            symbol        VARCHAR(50) NOT NULL,
            exchange      VARCHAR(20),
            quantity      BYTEA NOT NULL,      -- encrypted
            buying_price  BYTEA NOT NULL,      -- encrypted
            buying_date   DATE,
            target_price  BYTEA,               -- encrypted
            stop_loss     BYTEA,               -- encrypted
            notes         TEXT,
            created_at    TIMESTAMP DEFAULT now(),
            updated_at    TIMESTAMP DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_portfolio_holdings_symbol ON portfolio.holdings (symbol)")

    # audit_log — every access/action; NEVER stores financial values
    op.execute("""
        CREATE TABLE IF NOT EXISTS portfolio.audit_log (
            id          SERIAL PRIMARY KEY,
            action      VARCHAR(60) NOT NULL,
            ip_address  VARCHAR(64),
            "timestamp" TIMESTAMP DEFAULT now(),
            details     TEXT
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_portfolio_audit_ts ON portfolio.audit_log (\"timestamp\")")

    # Grant portfolio_user full access to the portfolio schema only (role created out-of-band).
    op.execute("""
        DO $$
        BEGIN
          IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'portfolio_user') THEN
            GRANT USAGE ON SCHEMA portfolio TO portfolio_user;
            GRANT ALL ON ALL TABLES IN SCHEMA portfolio TO portfolio_user;
            GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA portfolio TO portfolio_user;
            ALTER DEFAULT PRIVILEGES IN SCHEMA portfolio
              GRANT ALL ON TABLES TO portfolio_user;
            ALTER DEFAULT PRIVILEGES IN SCHEMA portfolio
              GRANT USAGE, SELECT ON SEQUENCES TO portfolio_user;
          END IF;
        END $$;
    """)

    # Explicitly deny the read-only webapp user any access to the portfolio schema.
    op.execute("""
        DO $$
        BEGIN
          IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'stock_reader') THEN
            REVOKE ALL ON SCHEMA portfolio FROM stock_reader;
            REVOKE ALL ON ALL TABLES IN SCHEMA portfolio FROM stock_reader;
          END IF;
        END $$;
    """)


def downgrade():
    op.execute("DROP SCHEMA IF EXISTS portfolio CASCADE")
