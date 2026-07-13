"""Backtest schema — Phase 1 vectorbt engine run storage.

Isolated `backtest` schema (mirrors the `portfolio` schema pattern), but with none of
portfolio's encryption/access restrictions — a backtest run is model performance over
PUBLIC market data, not real holdings/P&L, so it's fine for the read-only webapp role
to see it later.

runs           — one row per backtest run (strategy, universe, params, summary metrics)
equity_curve   — per-run daily portfolio value, for plotting
trades         — per-run individual round-trip trades

Revision ID: 0028
Revises: 0027
Create Date: 2026-07-12
"""
from alembic import op

revision = '0028'
down_revision = '0027'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS backtest")

    op.execute("""
        CREATE TABLE IF NOT EXISTS backtest.runs (
            id               SERIAL PRIMARY KEY,
            name             VARCHAR(120) NOT NULL,
            strategy_name    VARCHAR(80) NOT NULL,
            params           JSONB,
            universe         JSONB,          -- watchlist name + resolved stock_ids/symbols
            start_date       DATE NOT NULL,
            end_date         DATE NOT NULL,
            initial_capital  NUMERIC(18,2) NOT NULL,
            fees_pct         NUMERIC(8,6),
            slippage_pct     NUMERIC(8,6),
            metrics          JSONB,          -- cagr, sharpe, sortino, max_drawdown, hit_rate, turnover, ...
            status           VARCHAR(20) NOT NULL DEFAULT 'completed',
            error_message    TEXT,
            created_at       TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS backtest.equity_curve (
            id       SERIAL PRIMARY KEY,
            run_id   INTEGER NOT NULL REFERENCES backtest.runs(id) ON DELETE CASCADE,
            date     DATE NOT NULL,
            equity   NUMERIC(18,2) NOT NULL,
            UNIQUE (run_id, date)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_backtest_equity_run ON backtest.equity_curve (run_id, date)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS backtest.trades (
            id           SERIAL PRIMARY KEY,
            run_id       INTEGER NOT NULL REFERENCES backtest.runs(id) ON DELETE CASCADE,
            stock_id     INTEGER REFERENCES stocks(id),
            symbol       VARCHAR(50),
            entry_date   DATE,
            exit_date    DATE,
            entry_price  NUMERIC(14,4),
            exit_price   NUMERIC(14,4),
            size         NUMERIC(18,4),
            pnl          NUMERIC(18,2),
            return_pct   NUMERIC(10,4)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_backtest_trades_run ON backtest.trades (run_id)")

    # Read-only webapp role may read backtest results (public-market model performance,
    # unlike the portfolio schema which explicitly revokes this).
    op.execute("""
        DO $$
        BEGIN
          IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'stock_reader') THEN
            GRANT USAGE ON SCHEMA backtest TO stock_reader;
            GRANT SELECT ON ALL TABLES IN SCHEMA backtest TO stock_reader;
            ALTER DEFAULT PRIVILEGES IN SCHEMA backtest
              GRANT SELECT ON TABLES TO stock_reader;
          END IF;
        END $$;
    """)


def downgrade():
    op.execute("DROP SCHEMA IF EXISTS backtest CASCADE")
