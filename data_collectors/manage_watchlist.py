import psycopg2
import os
import sys
import zlib
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_collectors.nse_bhavcopy import latest_cm_bhavcopy, cm_rows_by_symbol

load_dotenv()

DB_PARAMS = {
    'dbname': 'stock_analyzer',
    'user': 'puneetgrover',
    'password': '',
    'host': 'localhost',
    'port': '5432'
}

EXCHANGE = 'NSE'


def _synthetic_token(isin):
    """Negative, collision-free instrument_token derived from the ISIN."""
    return -(zlib.crc32((isin or '').encode()) & 0x7fffffff)


def get_nse_symbol_master():
    """NSE equity symbol master {tradingsymbol: bhavcopy row} from the free CM bhavcopy."""
    _, rows = latest_cm_bhavcopy()
    return cm_rows_by_symbol(rows)

def add_to_watchlist(symbols, watchlist_name='Default'):
    """Add stocks to watchlist"""
    by_symbol = get_nse_symbol_master()
    conn = psycopg2.connect(**DB_PARAMS)
    cursor = conn.cursor()

    for symbol in symbols:
        row = by_symbol.get(symbol)
        if not row:
            print(f"✗ {symbol} not found")
            continue

        isin = (row.get('ISIN') or '').strip()
        name = (row.get('FinInstrmNm') or '').strip()
        # Add stock if not exists
        cursor.execute("""
            INSERT INTO stocks (instrument_token, exchange_token, tradingsymbol, name, exchange, segment, instrument_type, tick_size, lot_size, market)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (exchange, tradingsymbol) DO NOTHING
            RETURNING id
        """, (
            _synthetic_token(isin),
            isin,
            symbol,
            name,
            EXCHANGE,
            'NSE',
            'EQ',
            0.05,
            1,
            'NSE',
        ))

        result = cursor.fetchone()
        if result:
            stock_id = result[0]
        else:
            cursor.execute("SELECT id FROM stocks WHERE tradingsymbol = %s AND exchange = %s",
                         (symbol, EXCHANGE))
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
