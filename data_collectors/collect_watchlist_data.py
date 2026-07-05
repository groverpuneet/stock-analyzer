"""
data_collectors/collect_watchlist_data.py

Daily watchlist OHLCV collector — free NSE data (no brokerage).

Uses NSE's public CM bhavcopy archives (free, no brokerage auth) via the
shared data_collectors.nse_bhavcopy module.
"""
import os
import sys
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
import psycopg2

from data_collectors.nse_bhavcopy import (
    latest_cm_bhavcopy,
    fetch_cm_bhavcopy,
    cm_rows_by_symbol,
    parse_ohlcv,
)

load_dotenv()

DB_PARAMS = {
    'dbname': 'stock_analyzer',
    'user': 'puneetgrover',
    'password': '',
    'host': 'localhost',
    'port': '5432'
}


def get_watchlist_stocks(watchlist_name='Default'):
    conn = psycopg2.connect(**DB_PARAMS)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT s.id, s.instrument_token, s.tradingsymbol, s.name
        FROM watchlist w
        JOIN stocks s ON w.stock_id = s.id
        WHERE w.name = %s
        ORDER BY s.tradingsymbol
    """, (watchlist_name,))

    stocks = cursor.fetchall()
    cursor.close()
    conn.close()

    return stocks


def add_historical_data(cursor, stock_id, historical_data):
    """Upsert daily candles. Each candle's 'date' is a plain datetime.date."""
    count = 0
    for candle in historical_data:
        cursor.execute("""
            INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (stock_id, date) DO UPDATE
            SET open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume
        """, (
            stock_id,
            candle['date'],
            candle['open'],
            candle['high'],
            candle['low'],
            candle['close'],
            candle['volume']
        ))
        count += 1
    return count


def add_quote_data(cursor, stock_id, quote_data):
    """
    Insert a minimal post-close quote row derived from the bhavcopy.
    Brokerage-only fields (buy/sell qty, oi, circuit limits) are NULL.
    """
    ohlc = quote_data.get('ohlc') or {}
    cursor.execute("""
        INSERT INTO quotes (
            stock_id, timestamp, last_price, volume,
            buy_quantity, sell_quantity, oi,
            lower_circuit_limit, upper_circuit_limit,
            ohlc_open, ohlc_high, ohlc_low, ohlc_close
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        stock_id,
        datetime.now(),
        quote_data.get('last_price'),
        quote_data.get('volume'),
        quote_data.get('buy_quantity'),
        quote_data.get('sell_quantity'),
        quote_data.get('oi'),
        quote_data.get('lower_circuit_limit'),
        quote_data.get('upper_circuit_limit'),
        ohlc.get('open'),
        ohlc.get('high'),
        ohlc.get('low'),
        ohlc.get('close'),
    ))


def _collect_bhavcopies(days):
    """
    Return a list of (trading_date, rows) for the most recent `days` trading
    days, newest first. Walks back over weekends/holidays; caps the look-back
    at ~days*3 calendar days.
    """
    collected = []

    # Start from the most recent available bhavcopy (walks over today's holiday).
    start_dt, start_rows = latest_cm_bhavcopy()
    collected.append((start_dt, start_rows))

    dt = start_dt - timedelta(days=1)
    horizon = start_dt - timedelta(days=max(days * 3, 7))
    while len(collected) < days and dt >= horizon:
        if dt.weekday() < 5:  # skip Sat/Sun
            try:
                rows = fetch_cm_bhavcopy(dt)
                if rows:
                    collected.append((dt, rows))
            except Exception:
                pass  # 404 / holiday — skip
        dt = dt - timedelta(days=1)

    return collected


def collect_data(watchlist_name='Default', days=5, include_quotes=True):
    conn = psycopg2.connect(**DB_PARAMS)
    cursor = conn.cursor()

    stocks = get_watchlist_stocks(watchlist_name)

    if not stocks:
        print(f"No stocks in {watchlist_name} watchlist")
        cursor.close()
        conn.close()
        return

    print(f"\nCollecting data for {len(stocks)} stocks")
    print("=" * 60)

    # symbol -> stock_id for the watchlist
    stock_map = {symbol: stock_id for stock_id, _token, symbol, _name in stocks}
    watch_symbols = set(stock_map)

    days_data = _collect_bhavcopies(days)
    print(f"Fetched {len(days_data)} trading day(s) of bhavcopy: "
          f"{', '.join(str(d) for d, _ in days_data)}")

    # Accumulate candles per stock across all fetched days.
    candles_by_stock = {}
    for dt, rows in days_data:
        by_symbol = cm_rows_by_symbol(rows)
        for symbol in watch_symbols:
            row = by_symbol.get(symbol)
            if not row:
                continue
            candle = parse_ohlcv(row)
            candles_by_stock.setdefault(stock_map[symbol], []).append(candle)

    total_rows = 0
    for stock_id, candles in candles_by_stock.items():
        total_rows += add_historical_data(cursor, stock_id, candles)
    print(f"  ✓ Historical: {total_rows} rows across {len(candles_by_stock)} stocks")

    if include_quotes and days_data:
        # Minimal post-close quotes from the LATEST day's bhavcopy.
        try:
            latest_dt, latest_rows = days_data[0]
            latest_by_symbol = cm_rows_by_symbol(latest_rows)
            q_count = 0
            for symbol, stock_id in stock_map.items():
                row = latest_by_symbol.get(symbol)
                if not row:
                    continue
                p = parse_ohlcv(row)
                quote_data = {
                    'last_price': p['close'],
                    'volume': p['volume'],
                    'ohlc': {
                        'open': p['open'],
                        'high': p['high'],
                        'low': p['low'],
                        'close': p['close'],
                    },
                }
                add_quote_data(cursor, stock_id, quote_data)
                q_count += 1
            print(f"  ✓ Quotes saved: {q_count} stocks (from {latest_dt})")
        except Exception as e:
            print(f"  ✗ Quote error (non-fatal): {e}")

    conn.commit()
    cursor.close()
    conn.close()

    print("\n" + "=" * 60)
    print("✓ Complete!")


if __name__ == "__main__":
    days = 5
    include_quotes = '--quotes' in sys.argv or '--no-quotes' not in sys.argv

    for arg in sys.argv[1:]:
        if arg.isdigit():
            days = int(arg)

    print("\n" + "=" * 60)
    print("WATCHLIST DATA COLLECTOR")
    print("=" * 60)
    print(f"Days: {days}")
    print(f"Quotes: {include_quotes}")

    collect_data(days=days, include_quotes=include_quotes)
