import psycopg2
from kiteconnect import KiteConnect
import os
from dotenv import load_dotenv

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
    return kite

def add_to_watchlist(symbols, watchlist_name='Default'):
    """Add stocks to watchlist"""
    kite = get_kite_client()
    conn = psycopg2.connect(**DB_PARAMS)
    cursor = conn.cursor()
    
    instruments = kite.instruments('NSE')
    
    for symbol in symbols:
        instrument = next((i for i in instruments if i['tradingsymbol'] == symbol), None)
        if not instrument:
            print(f"✗ {symbol} not found")
            continue
        
        # Add stock if not exists
        cursor.execute("""
            INSERT INTO stocks (instrument_token, exchange_token, tradingsymbol, name, exchange, segment, instrument_type, tick_size, lot_size)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (exchange, tradingsymbol) DO NOTHING
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
        
        result = cursor.fetchone()
        if result:
            stock_id = result[0]
        else:
            cursor.execute("SELECT id FROM stocks WHERE tradingsymbol = %s AND exchange = %s", 
                         (instrument['tradingsymbol'], instrument['exchange']))
            stock_id = cursor.fetchone()[0]
        
        # Add to watchlist
        cursor.execute("""
            INSERT INTO watchlist (stock_id, name)
            VALUES (%s, %s)
            ON CONFLICT (stock_id, name) DO NOTHING
        """, (stock_id, watchlist_name))
        
        print(f"✓ {symbol} added to {watchlist_name}")
    
    conn.commit()
    cursor.close()
    conn.close()

def view_watchlist(watchlist_name='Default'):
    """View stocks in watchlist"""
    conn = psycopg2.connect(**DB_PARAMS)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT s.tradingsymbol, s.name, w.notes
        FROM watchlist w
        JOIN stocks s ON w.stock_id = s.id
        WHERE w.name = %s
        ORDER BY s.tradingsymbol
    """, (watchlist_name,))
    
    stocks = cursor.fetchall()
    
    print(f"\n{watchlist_name} Watchlist:")
    print("="*60)
    for symbol, name, notes in stocks:
        print(f"{symbol:15} {name[:40]:40}")
        if notes:
            print(f"                Notes: {notes}")
    
    cursor.close()
    conn.close()

def remove_from_watchlist(symbols, watchlist_name='Default'):
    """Remove stocks from watchlist"""
    conn = psycopg2.connect(**DB_PARAMS)
    cursor = conn.cursor()
    
    for symbol in symbols:
        cursor.execute("""
            DELETE FROM watchlist w
            USING stocks s
            WHERE w.stock_id = s.id 
            AND s.tradingsymbol = %s 
            AND w.name = %s
        """, (symbol, watchlist_name))
        
        if cursor.rowcount > 0:
            print(f"✓ {symbol} removed from {watchlist_name}")
        else:
            print(f"✗ {symbol} not in {watchlist_name}")
    
    conn.commit()
    cursor.close()
    conn.close()

if __name__ == "__main__":
    # Example: Add popular stocks to default watchlist
    popular_stocks = [
        'RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK',
        'BHARTIARTL', 'SBIN', 'WIPRO', 'ITC', 'KOTAKBANK'
    ]
    
    print("\nAdding stocks to watchlist...")
    add_to_watchlist(popular_stocks)
    
    print("\n")
    view_watchlist()
