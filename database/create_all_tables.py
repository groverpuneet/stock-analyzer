import psycopg2

DB_PARAMS = {
    'dbname': 'stock_analyzer',
    'user': 'puneetgrover',
    'password': '',
    'host': 'localhost',
    'port': '5432'
}

conn = psycopg2.connect(**DB_PARAMS)
cursor = conn.cursor()

# Enhanced stocks table
cursor.execute("DROP TABLE IF EXISTS stocks CASCADE")
cursor.execute("""
    CREATE TABLE stocks (
        id SERIAL PRIMARY KEY,
        instrument_token BIGINT UNIQUE NOT NULL,
        exchange_token VARCHAR(20),
        tradingsymbol VARCHAR(100) NOT NULL,
        name VARCHAR(200),
        exchange VARCHAR(10) NOT NULL,
        segment VARCHAR(20),
        instrument_type VARCHAR(20),
        tick_size DECIMAL(10, 4),
        lot_size INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(exchange, tradingsymbol)
    )
""")
print("✓ stocks")

# Daily prices
cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_prices (
        id SERIAL PRIMARY KEY,
        stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
        date DATE NOT NULL,
        open DECIMAL(12, 2),
        high DECIMAL(12, 2),
        low DECIMAL(12, 2),
        close DECIMAL(12, 2),
        volume BIGINT,
        UNIQUE(stock_id, date)
    )
""")
print("✓ daily_prices")

# Quotes
cursor.execute("DROP TABLE IF EXISTS quotes CASCADE")
cursor.execute("""
    CREATE TABLE quotes (
        id SERIAL PRIMARY KEY,
        stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
        timestamp TIMESTAMP NOT NULL,
        last_price DECIMAL(12, 2),
        volume BIGINT,
        buy_quantity BIGINT,
        sell_quantity BIGINT,
        oi BIGINT,
        lower_circuit_limit DECIMAL(12, 2),
        upper_circuit_limit DECIMAL(12, 2),
        ohlc_open DECIMAL(12, 2),
        ohlc_high DECIMAL(12, 2),
        ohlc_low DECIMAL(12, 2),
        ohlc_close DECIMAL(12, 2)
    )
""")
print("✓ quotes")

# Fundamentals
cursor.execute("""
    CREATE TABLE IF NOT EXISTS fundamentals (
        id SERIAL PRIMARY KEY,
        stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
        date DATE NOT NULL,
        market_cap DECIMAL(15, 2),
        pe_ratio DECIMAL(10, 2),
        pb_ratio DECIMAL(10, 2),
        roe DECIMAL(5, 2),
        debt_to_equity DECIMAL(10, 2),
        eps DECIMAL(10, 2),
        UNIQUE(stock_id, date)
    )
""")
print("✓ fundamentals")

# Technical indicators
cursor.execute("""
    CREATE TABLE IF NOT EXISTS technical_indicators (
        id SERIAL PRIMARY KEY,
        stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
        date DATE NOT NULL,
        rsi_14 DECIMAL(5, 2),
        sma_20 DECIMAL(12, 2),
        sma_50 DECIMAL(12, 2),
        sma_200 DECIMAL(12, 2),
        UNIQUE(stock_id, date)
    )
""")
print("✓ technical_indicators")

conn.commit()
print("\n✓ All tables created!")
