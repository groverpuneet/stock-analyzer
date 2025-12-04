import os
from kiteconnect import KiteConnect
from dotenv import load_dotenv
import psycopg2
from datetime import datetime, timedelta

load_dotenv()

DB_PARAMS = {
    'dbname': 'stock_analyzer',
    'user': os.environ.get('USER', 'puneetgrover'),
    'password': '',
    'host': 'localhost',
    'port': '5432'
}

def get_kite_client():
    with open('.kite_access_token', 'r') as f:
        access_token = f.read().strip()
    
    kite = KiteConnect(api_key=os.getenv('KITE_API_KEY'))
    kite.set_access_token(access_token)
    return kite

def add_stock(cursor, instrument):
    cursor.execute("""
        INSERT INTO stocks (instrument_token, exchange_token, tradingsymbol, name, exchange, segment, instrument_type, tick_size, lot_size)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (exchange, tradingsymbol) DO UPDATE
        SET instrument_token = EXCLUDED.instrument_token,
            name = EXCLUDED.name,
            updated_at = CURRENT_TIMESTAMP
        RETURNING id
    """, (
        instrument['instrument_token'],
        instrument.get('exchange_token', ''),
        instrument['tradingsymbol'],
        instrument['name'],
        instrument['exchange'],
        instrument.get('segment', ''),
        instrument.get('instrument_type', ''),
        instrument.get('tick_size', 0),
        instrument.get('lot_size', 1)
    ))
    return cursor.fetchone()[0]

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

def collect_data(symbols, days=30):
    kite = get_kite_client()
    conn = psycopg2.connect(**DB_PARAMS)
    cursor = conn.cursor()
    
    print("\nFetching instrument list...")
    instruments = kite.instruments('NSE')
    print(f"✓ Got {len(instruments)} instruments")
    
    to_date = datetime.now()
    from_date = to_date - timedelta(days=days)
    
    for symbol in symbols:
        print(f"\nProcessing {symbol}...")
        
        instrument = next((i for i in instruments if i['tradingsymbol'] == symbol), None)
        if not instrument:
            print(f"  ✗ Not found")
            continue
        
        stock_id = add_stock(cursor, instrument)
        print(f"  ✓ Stock ID: {stock_id}")
        
        try:
            historical = kite.historical_data(
                instrument_token=instrument['instrument_token'],
                from_date=from_date,
                to_date=to_date,
                interval='day'
            )
            
            count = add_historical_data(cursor, stock_id, historical)
            print(f"  ✓ {count} days added")
            
        except Exception as e:
            print(f"  ✗ Error: {e}")
    
    conn.commit()
    cursor.close()
    conn.close()
    print("\n✓ Complete!")

if __name__ == "__main__":
    symbols = ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK']
    print("\n" + "="*60)
    print("KITE DATA COLLECTOR")
    print("="*60)
    collect_data(symbols, days=30)
