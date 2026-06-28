import os
import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime

# Honour DATABASE_URL so this works inside the Dagster container (host.docker.internal)
# as well as locally. Falls back to the local host DB.
_DSN = os.environ.get("DATABASE_URL", "postgresql://puneetgrover@localhost/stock_analyzer")

DB_PARAMS = {
    'dbname': 'stock_analyzer',
    'user': 'puneetgrover',
    'password': '',
    'host': 'localhost',
    'port': '5432'
}


def _connect():
    return psycopg2.connect(_DSN)


def get_stock_prices(stock_id, limit=200):
    """Get historical prices for a stock"""
    conn = _connect()
    
    query = """
        SELECT date, open, high, low, close, volume
        FROM daily_prices
        WHERE stock_id = %s
        ORDER BY date DESC
        LIMIT %s
    """
    
    df = pd.read_sql_query(query, conn, params=(stock_id, limit))
    conn.close()
    
    # Sort chronologically for calculations
    df = df.sort_values('date').reset_index(drop=True)
    return df

def calculate_sma(prices, period):
    """Simple Moving Average"""
    return prices.rolling(window=period).mean()

def calculate_ema(prices, period):
    """Exponential Moving Average"""
    return prices.ewm(span=period, adjust=False).mean()

def calculate_rsi(prices, period=14):
    """Relative Strength Index"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_macd(prices, fast=12, slow=26, signal=9):
    """MACD (Moving Average Convergence Divergence)"""
    ema_fast = calculate_ema(prices, fast)
    ema_slow = calculate_ema(prices, slow)
    
    macd = ema_fast - ema_slow
    macd_signal = calculate_ema(macd, signal)
    macd_histogram = macd - macd_signal
    
    return macd, macd_signal, macd_histogram

def calculate_bollinger_bands(prices, period=20, std_dev=2):
    """Bollinger Bands"""
    sma = calculate_sma(prices, period)
    std = prices.rolling(window=period).std()
    
    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)
    
    return upper, sma, lower

def calculate_all_indicators(stock_id, stock_symbol):
    """Calculate all indicators for a stock"""
    print(f"\n{stock_symbol}:")
    
    # Get price data
    df = get_stock_prices(stock_id, limit=200)
    
    if len(df) < 50:
        print(f"  ✗ Not enough data (need 50+ days, have {len(df)})")
        return
    
    # Calculate indicators
    df['sma_20'] = calculate_sma(df['close'], 20)
    df['sma_50'] = calculate_sma(df['close'], 50)
    df['sma_200'] = calculate_sma(df['close'], 200)
    
    df['ema_12'] = calculate_ema(df['close'], 12)
    df['ema_26'] = calculate_ema(df['close'], 26)
    
    df['rsi_14'] = calculate_rsi(df['close'], 14)
    
    macd, macd_signal, macd_hist = calculate_macd(df['close'])
    df['macd'] = macd
    df['macd_signal'] = macd_signal
    df['macd_histogram'] = macd_hist
    
    upper, middle, lower = calculate_bollinger_bands(df['close'])
    df['bollinger_upper'] = upper
    df['bollinger_middle'] = middle
    df['bollinger_lower'] = lower
    
    # Store in database
    conn = _connect()
    cursor = conn.cursor()
    
    count = 0
    for _, row in df.iterrows():
        # Skip rows where we don't have all indicators
        if pd.isna(row['sma_20']):
            continue
        
        cursor.execute("""
            INSERT INTO technical_indicators (
                stock_id, date, rsi_14,
                sma_20, sma_50, sma_200,
                ema_12, ema_26,
                macd, macd_signal, macd_histogram,
                bollinger_upper, bollinger_middle, bollinger_lower
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (stock_id, date) DO UPDATE
            SET rsi_14 = EXCLUDED.rsi_14,
                sma_20 = EXCLUDED.sma_20,
                sma_50 = EXCLUDED.sma_50,
                sma_200 = EXCLUDED.sma_200,
                ema_12 = EXCLUDED.ema_12,
                ema_26 = EXCLUDED.ema_26,
                macd = EXCLUDED.macd,
                macd_signal = EXCLUDED.macd_signal,
                macd_histogram = EXCLUDED.macd_histogram,
                bollinger_upper = EXCLUDED.bollinger_upper,
                bollinger_middle = EXCLUDED.bollinger_middle,
                bollinger_lower = EXCLUDED.bollinger_lower
        """, (
            stock_id, row['date'], row['rsi_14'],
            row['sma_20'], row['sma_50'], row['sma_200'],
            row['ema_12'], row['ema_26'],
            row['macd'], row['macd_signal'], row['macd_histogram'],
            row['bollinger_upper'], row['bollinger_middle'], row['bollinger_lower']
        ))
        count += 1
    
    conn.commit()
    cursor.close()
    conn.close()
    
    print(f"  ✓ {count} days of indicators calculated")

def process_all_watchlist_stocks(watchlist_name='Default'):
    """Calculate indicators for all stocks in watchlist"""
    conn = _connect()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT s.id, s.tradingsymbol
        FROM watchlist w
        JOIN stocks s ON w.stock_id = s.id
        WHERE w.name = %s
        ORDER BY s.tradingsymbol
    """, (watchlist_name,))
    
    stocks = cursor.fetchall()
    cursor.close()
    conn.close()
    
    print(f"\nCalculating indicators for {len(stocks)} stocks")
    print("="*60)
    
    for stock_id, symbol in stocks:
        try:
            calculate_all_indicators(stock_id, symbol)
        except Exception as e:
            print(f"  ✗ Error: {e}")
    
    print("\n" + "="*60)
    print("✓ Indicator calculation complete!")


def recompute_queued_indicators():
    """Drain recompute_queue: recompute indicators for each queued stock, then clear
    exactly those rows. Items queued mid-run stay for the next pass. Returns a summary.
    """
    conn = _connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT q.stock_id, s.tradingsymbol
        FROM recompute_queue q JOIN stocks s ON s.id = q.stock_id
        ORDER BY q.queued_at
    """)
    queued = cur.fetchall()
    cur.close()
    conn.close()

    if not queued:
        return {"queued": 0, "recomputed": 0}

    done = []
    for stock_id, symbol in queued:
        try:
            calculate_all_indicators(stock_id, symbol)
            done.append(stock_id)
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {symbol}: {e}")

    if done:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("DELETE FROM recompute_queue WHERE stock_id = ANY(%s)", (done,))
        conn.commit()
        cur.close()
        conn.close()
    return {"queued": len(queued), "recomputed": len(done)}


if __name__ == "__main__":
    print("\n" + "="*60)
    print("TECHNICAL INDICATOR CALCULATOR")
    print("="*60)
    
    process_all_watchlist_stocks()
