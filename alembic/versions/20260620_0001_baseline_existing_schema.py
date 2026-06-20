"""Baseline existing schema.
Revision ID: 0001
Revises:
Create Date: 2026-06-20
"""
from alembic import op
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.execute("""CREATE TABLE IF NOT EXISTS stocks (
        id SERIAL PRIMARY KEY, instrument_token BIGINT UNIQUE NOT NULL,
        exchange_token VARCHAR(20), tradingsymbol VARCHAR(100) NOT NULL,
        name VARCHAR(200), exchange VARCHAR(10) NOT NULL, segment VARCHAR(20),
        instrument_type VARCHAR(20), tick_size DECIMAL(10,4), lot_size INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(exchange, tradingsymbol))""")
    op.execute("""CREATE TABLE IF NOT EXISTS daily_prices (
        id SERIAL PRIMARY KEY, stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
        date DATE NOT NULL, open DECIMAL(12,2), high DECIMAL(12,2),
        low DECIMAL(12,2), close DECIMAL(12,2), volume BIGINT, UNIQUE(stock_id, date))""")
    op.execute("""CREATE TABLE IF NOT EXISTS quotes (
        id SERIAL PRIMARY KEY, stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
        timestamp TIMESTAMP NOT NULL, last_price DECIMAL(12,2), volume BIGINT,
        buy_quantity BIGINT, sell_quantity BIGINT, oi BIGINT,
        lower_circuit_limit DECIMAL(12,2), upper_circuit_limit DECIMAL(12,2),
        ohlc_open DECIMAL(12,2), ohlc_high DECIMAL(12,2),
        ohlc_low DECIMAL(12,2), ohlc_close DECIMAL(12,2))""")
    op.execute("""CREATE TABLE IF NOT EXISTS fundamentals (
        id SERIAL PRIMARY KEY, stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
        date DATE NOT NULL, market_cap DECIMAL(15,2), pe_ratio DECIMAL(10,2),
        pb_ratio DECIMAL(10,2), roe DECIMAL(5,2), debt_to_equity DECIMAL(10,2),
        eps DECIMAL(10,2), UNIQUE(stock_id, date))""")
    op.execute("""CREATE TABLE IF NOT EXISTS technical_indicators (
        id SERIAL PRIMARY KEY, stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
        date DATE NOT NULL, rsi_14 DECIMAL(5,2), sma_20 DECIMAL(12,2),
        sma_50 DECIMAL(12,2), sma_200 DECIMAL(12,2), UNIQUE(stock_id, date))""")
    op.execute("""CREATE TABLE IF NOT EXISTS watchlist (
        id SERIAL PRIMARY KEY, name VARCHAR(100) NOT NULL,
        stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
        UNIQUE(name, stock_id))""")

def downgrade():
    for t in ['technical_indicators','fundamentals','quotes',
              'daily_prices','watchlist','stocks']:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
