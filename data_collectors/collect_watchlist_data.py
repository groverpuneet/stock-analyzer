import os
from kiteconnect import KiteConnect
from dotenv import load_dotenv
import psycopg2
from datetime import datetime, timedelta
from kite_auth.readonly_kite import wrap_readonly

load_dotenv()

DB_PARAMS = {
    'dbname': 'stock_analyzer',
    'user': 'puneetgrover',
    'password': '',
    'host': 'localhost',
    'port': '5432'
}

def get_kite_client():
    with open('.kite_access_token', 'r') as f:
        access_token = f.read().strip()
    kite = KiteConnect(api_key=os.getenv('KITE_API_KEY'))
    kite.set_access_token(access_token)
    return wrap_readonly(kite)

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
            candle['date'].date(),
            candle['open'],
            candle['high'],
            candle['low'],
            candle['close'],
            candle['volume']
        ))
        count += 1
    return count

def add_quote_data(cursor, stock_id, quote_data):
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
        quote_data['ohlc'].get('open'),
        quote_data['ohlc'].get('high'),
        quote_data['ohlc'].get('low'),
        quote_data['ohlc'].get('close')
    ))

def collect_data(watchlist_name='Default', days=30, include_quotes=False):
    kite = get_kite_client()
    conn = psycopg2.connect(**DB_PARAMS)
    cursor = conn.cursor()
    
    stocks = get_watchlist_stocks(watchlist_name)
    
    if not stocks:
        print(f"No stocks in {watchlist_name} watchlist")
        return
    
    print(f"\nCollecting data for {len(stocks)} stocks")
    print("="*60)
    
    to_date = datetime.now()
    from_date = to_date - timedelta(days=days)
    
    quote_symbols = []
    stock_map = {}
    
    for stock_id, instrument_token, symbol, name in stocks:
        print(f"\n{symbol}:")
        quote_symbols.append(f"NSE:{symbol}")
        stock_map[f"NSE:{symbol}"] = stock_id
        
        try:
            historical = kite.historical_data(
                instrument_token=instrument_token,
                from_date=from_date,
                to_date=to_date,
                interval='day'
            )
            
            count = add_historical_data(cursor, stock_id, historical)
            print(f"  ✓ Historical: {count} days")
            
        except Exception as e:
            print(f"  ✗ Error: {e}")
    
    if include_quotes:
        print(f"\nFetching quotes...")
        try:
            quotes = kite.quote(quote_symbols)
            for symbol, quote_data in quotes.items():
                stock_id = stock_map[symbol]
                add_quote_data(cursor, stock_id, quote_data)
            print(f"✓ Quotes saved: {len(quotes)} stocks")
        except Exception as e:
            print(f"✗ Quote error: {e}")
    
    conn.commit()
    cursor.close()
    conn.close()
    
    print("\n" + "="*60)
    print("✓ Complete!")

if __name__ == "__main__":
    import sys
    
    days = 30
    include_quotes = '--quotes' in sys.argv
    
    # Get days if provided as number
    for arg in sys.argv[1:]:
        if arg.isdigit():
            days = int(arg)
    
    print("\n" + "="*60)
    print("WATCHLIST DATA COLLECTOR")
    print("="*60)
    print(f"Days: {days}")
    print(f"Quotes: {include_quotes}")
    
    collect_data(days=days, include_quotes=include_quotes)
