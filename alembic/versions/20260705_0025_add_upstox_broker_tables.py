"""Upstox broker-data tables — F&O contract master, intraday bars, option chain.

Adds the capability the free-scrape spine never had at contract level:
  - fno_instruments        — per-contract F&O master (strike/expiry/type). `stocks`
                             cannot model these (no strike/expiry columns).
  - intraday_prices        — minute/hour OHLCV. daily_prices is EOD-only.
  - option_chain_snapshots — per-strike option chain with server-side Greeks + OI.

Also extends `stocks` with `isin` + `instrument_key` so Upstox historical-candle
calls (keyed by Upstox instrument_key, not Kite's numeric token) can resolve a symbol.

Data plane only — populated by the order-incapable Upstox Analytics token. The
`source` tag lives in data_refresh_log.source (seeded below), never on the rows.

Revision ID: 0025
Revises: 0024
Create Date: 2026-07-05
"""
from alembic import op

revision = '0025'
down_revision = '0024'
branch_labels = None
depends_on = None


def upgrade():
    # --- Extend the equity master so Upstox candle calls can resolve a symbol -----
    op.execute("ALTER TABLE stocks ADD COLUMN IF NOT EXISTS isin VARCHAR(12)")
    op.execute("ALTER TABLE stocks ADD COLUMN IF NOT EXISTS instrument_key VARCHAR(60)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_stocks_instrument_key ON stocks (instrument_key)")

    # --- 1. F&O contract master (futures + options) ------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS fno_instruments (
            id                SERIAL PRIMARY KEY,
            instrument_key    VARCHAR(60) NOT NULL,      -- Upstox key, e.g. "NSE_FO|54876"
            exchange_token    BIGINT,
            tradingsymbol     VARCHAR(60) NOT NULL,
            name              VARCHAR(60),               -- underlying name
            underlying_symbol VARCHAR(30) NOT NULL,      -- NIFTY, RELIANCE, ...
            underlying_key    VARCHAR(60),               -- Upstox key of the underlying
            underlying_type   VARCHAR(10),               -- INDEX / EQUITY
            exchange          VARCHAR(10) NOT NULL,      -- NSE / BSE
            segment           VARCHAR(10) NOT NULL,      -- NFO / BFO
            instrument_type   VARCHAR(4)  NOT NULL,      -- FUT / CE / PE
            expiry            DATE NOT NULL,
            strike            DECIMAL(12,2),             -- NULL for FUT
            lot_size          INTEGER,
            tick_size         DECIMAL(8,2),
            freeze_quantity   INTEGER,
            isin              VARCHAR(12),
            source            VARCHAR(20) NOT NULL DEFAULT 'upstox_instruments',
            created_at        TIMESTAMPTZ DEFAULT NOW(),
            updated_at        TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT uq_fno_instruments_key UNIQUE (instrument_key)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_fno_instruments_underlying_expiry "
               "ON fno_instruments (underlying_symbol, expiry)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_fno_instruments_expiry_type "
               "ON fno_instruments (expiry, instrument_type)")

    # --- 2. Intraday OHLCV bars (equity + F&O) -----------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS intraday_prices (
            id              BIGSERIAL PRIMARY KEY,
            instrument_key  VARCHAR(60) NOT NULL,        -- matches stocks/fno_instruments
            ts              TIMESTAMPTZ NOT NULL,         -- bar start time
            interval        VARCHAR(8)  NOT NULL,        -- 1m / 5m / 15m / 30m / 60m
            open            DECIMAL(14,2),
            high            DECIMAL(14,2),
            low             DECIMAL(14,2),
            close           DECIMAL(14,2),
            volume          BIGINT,
            oi              BIGINT,                      -- populated for F&O
            source          VARCHAR(20) NOT NULL DEFAULT 'upstox_intraday',
            CONSTRAINT uq_intraday_key_interval_ts UNIQUE (instrument_key, interval, ts)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_intraday_key_ts ON intraday_prices (instrument_key, ts)")

    # --- 3. Option-chain snapshots with Greeks + OI ------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS option_chain_snapshots (
            id                BIGSERIAL PRIMARY KEY,
            snapshot_ts       TIMESTAMPTZ NOT NULL,      -- when the chain was pulled
            underlying_symbol VARCHAR(30) NOT NULL,      -- NIFTY / RELIANCE
            expiry            DATE NOT NULL,
            strike            DECIMAL(12,2) NOT NULL,
            option_type       VARCHAR(2)  NOT NULL,      -- CE / PE
            instrument_key    VARCHAR(60),               -- -> fno_instruments.instrument_key
            underlying_spot   DECIMAL(14,2),
            last_price        DECIMAL(14,2),
            volume            BIGINT,
            oi                BIGINT,
            prev_oi           BIGINT,
            iv                DECIMAL(8,4),              -- implied volatility
            delta             DECIMAL(8,4),
            gamma             DECIMAL(10,6),
            theta             DECIMAL(10,4),
            vega              DECIMAL(10,4),
            pop               DECIMAL(8,4),              -- Upstox probability-of-profit
            bid_price         DECIMAL(14,2),
            bid_qty           BIGINT,
            ask_price         DECIMAL(14,2),
            ask_qty           BIGINT,
            source            VARCHAR(20) NOT NULL DEFAULT 'upstox_option_chain',
            CONSTRAINT uq_option_chain_snap
                UNIQUE (snapshot_ts, underlying_symbol, expiry, strike, option_type)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_option_chain_underlying_expiry "
               "ON option_chain_snapshots (underlying_symbol, expiry, snapshot_ts)")

    # --- 4. Seed data_refresh_log source tags (refresh_log is UPDATE-only) -------
    op.execute("""
        INSERT INTO data_refresh_log (source, tier, status, rows_upserted) VALUES
            ('upstox_instruments',  'daily',    'never_run', 0),
            ('upstox_ohlcv',        'daily',    'never_run', 0),
            ('upstox_quotes',       'realtime', 'never_run', 0),
            ('upstox_intraday',     'realtime', 'never_run', 0),
            ('upstox_option_chain', 'realtime', 'never_run', 0)
        ON CONFLICT (source) DO NOTHING
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS option_chain_snapshots")
    op.execute("DROP TABLE IF EXISTS intraday_prices")
    op.execute("DROP TABLE IF EXISTS fno_instruments")
    op.execute("DROP INDEX IF EXISTS idx_stocks_instrument_key")
    op.execute("ALTER TABLE stocks DROP COLUMN IF EXISTS instrument_key")
    op.execute("ALTER TABLE stocks DROP COLUMN IF EXISTS isin")
    op.execute("""
        DELETE FROM data_refresh_log WHERE source IN
            ('upstox_instruments','upstox_ohlcv','upstox_quotes',
             'upstox_intraday','upstox_option_chain')
    """)
