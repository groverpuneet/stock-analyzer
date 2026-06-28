"""
data_collectors/google_trends_collector.py

Collects Google Search interest (0–100 relative score) for NSE watchlist stocks.
Stored in macro_indicators with indicator='google_trends_{SYMBOL}'.

Approach:
  - Queries Google Trends via pytrends for each stock by company name
  - Processes in batches of 5 (pytrends limit)
  - Stores all available dates from the last 90 days on first run,
    last 7 days on subsequent runs
  - ON CONFLICT upserts to handle re-runs

Schedule: Weekly Sunday 07:30 IST (nse_weekly group in Dagster)
Source: Google Trends India (geo='IN')
"""
import os
import sys
import time
import logging
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.db import get_conn, refresh_log, get_watchlist_stocks

log = logging.getLogger(__name__)

# Company name overrides for better Google Trends matching
# Default: use stocks.name field (cleaned up)
_NAME_OVERRIDES = {
    'BHARTIARTL': 'Bharti Airtel',
    'HDFCBANK':   'HDFC Bank',
    'ICICIBANK':  'ICICI Bank',
    'INFY':       'Infosys',
    'ITC':        'ITC',
    'KOTAKBANK':  'Kotak Mahindra Bank',
    'RELIANCE':   'Reliance Industries',
    'SBIN':       'State Bank of India',
    'TCS':        'Tata Consultancy Services',
    'WIPRO':      'Wipro',
}

BATCH_SIZE = 5
REQUEST_DELAY = 3.0  # seconds between pytrends batches (rate limit)


def _search_term(symbol: str, name: str) -> str:
    """Return Google search term for a stock."""
    if symbol in _NAME_OVERRIDES:
        return _NAME_OVERRIDES[symbol]
    return name.strip().title()


def _last_stored_date(conn, symbol: str):
    """Return the most recent date already stored for this symbol."""
    cur = conn.cursor()
    cur.execute(
        "SELECT MAX(date) FROM macro_indicators WHERE indicator = %s",
        (f'google_trends_{symbol}',)
    )
    result = cur.fetchone()[0]
    cur.close()
    return result


def _store_batch(conn, batch_df, symbol_map: dict) -> int:
    """Upsert rows from a pytrends DataFrame into macro_indicators."""
    cur = conn.cursor()
    stored = 0
    for col_name, symbol in symbol_map.items():
        if col_name not in batch_df.columns:
            continue
        for dt, row in batch_df.iterrows():
            if row.get('isPartial', False):
                continue  # skip incomplete/partial day
            val = row[col_name]
            if val is None:
                continue
            cur.execute("""
                INSERT INTO macro_indicators (date, market, indicator, value, unit, period, source)
                VALUES (%s, 'IN', %s, %s, 'index', 'daily', 'google_trends')
                ON CONFLICT (date, market, indicator) DO UPDATE SET
                    value  = EXCLUDED.value,
                    source = EXCLUDED.source
            """, (dt.date(), f'google_trends_{symbol}', float(val)))
            stored += 1
    conn.commit()
    cur.close()
    return stored


def collect_google_trends(watchlist_name: str = 'Default') -> dict:
    """
    Collect Google Trends interest for all stocks in the watchlist.
    Returns {'rows_upserted': int, 'stocks_processed': int}.
    """
    try:
        from pytrends.request import TrendReq
    except ImportError:
        log.error("pytrends not installed — run: pip install pytrends")
        return {'rows_upserted': 0, 'stocks_processed': 0}

    stocks = get_watchlist_stocks(watchlist_name)
    if not stocks:
        log.warning(f"No stocks in watchlist '{watchlist_name}'")
        return {'rows_upserted': 0, 'stocks_processed': 0}

    conn = get_conn()
    total_stored = 0
    stocks_done = 0

    with refresh_log('google_trends') as meta:
        pytrends = TrendReq(hl='en-IN', tz=330)

        # Build list of (symbol, search_term) pairs
        stock_list = [(sym, _search_term(sym, name)) for _, _, sym, name in stocks]

        # Determine timeframe: 3 months on first run, 1 month subsequently
        any_stored = any(_last_stored_date(conn, sym) for sym, _ in stock_list)
        timeframe = 'today 1-m' if any_stored else 'today 3-m'
        log.info(f"Google Trends timeframe: {timeframe} for {len(stock_list)} stocks")

        # Process in batches of BATCH_SIZE
        for i in range(0, len(stock_list), BATCH_SIZE):
            batch = stock_list[i:i + BATCH_SIZE]
            search_terms = [term for _, term in batch]
            symbol_map = {term: sym for sym, term in batch}

            log.info(f"  Fetching batch {i//BATCH_SIZE + 1}: {search_terms}")
            try:
                pytrends.build_payload(search_terms, timeframe=timeframe, geo='IN')
                df = pytrends.interest_over_time()
                if df.empty:
                    log.warning(f"  Empty response for batch {search_terms}")
                else:
                    n = _store_batch(conn, df, symbol_map)
                    total_stored += n
                    stocks_done += len(batch)
                    log.info(f"  Stored {n} rows for {search_terms}")
            except Exception as e:
                log.warning(f"  Batch failed: {e}")

            if i + BATCH_SIZE < len(stock_list):
                time.sleep(REQUEST_DELAY)

        meta['rows'] = total_stored

    conn.close()
    log.info(f"Google Trends done: {total_stored} rows upserted for {stocks_done} stocks")
    return {'rows_upserted': total_stored, 'stocks_processed': stocks_done}


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    result = collect_google_trends()
    print(f"Done: {result}")
