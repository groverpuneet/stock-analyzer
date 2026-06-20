"""
data_collectors/screener_collector.py
Weekly refresh — Sunday 8:00 AM IST

Fetches fundamentals from Screener.in public pages (no auth required for basic data).
Fields collected: P/E, P/B, ROE, ROCE, OPM, NPM, Debt/Equity, Promoter holding,
                  EPS, Book Value, Dividend Yield, Market Cap, Current Ratio.

Usage:
    python data_collectors/screener_collector.py
"""
import requests
from bs4 import BeautifulSoup
import psycopg2
import time
import sys
import os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.db import get_conn, refresh_log, get_watchlist_stocks

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}

BASE_URL = "https://www.screener.in/company/{symbol}/consolidated/"

# Map Screener.in label text → our DB column
RATIO_MAP = {
    'Market Cap':          'market_cap',
    'Current Price':       None,                  # skip, we have it from Kite
    'High / Low':          None,
    'Stock P/E':           'pe_ratio',
    'Book Value':          'book_value',
    'Dividend Yield':      'dividend_yield_pct',
    'ROCE':                'roce_pct',
    'ROE':                 'roe',
    'Face Value':          'face_value',
    'P/B':                 'pb_ratio',
    'EPS (TTM)':           'eps',
    'Debt to equity':      'debt_to_equity',
    'Current ratio':       'current_ratio',
    'Quick ratio':         'quick_ratio',
    'Peg ratio':           'peg_ratio',
    'EV/EBITDA':           'ev_ebitda',
    'OPM':                 'opm_pct',
    'NPM':                 'npm_pct',
    'Promoter holding':    'promoter_holding_pct',
    '% Pledged':           'pledged_pct',
}


def _parse_number(text: str):
    """Parse '12,345.67 Cr' or '23.4%' into a float, return None on failure."""
    if not text:
        return None
    # strip units
    text = text.replace(',', '').replace('%', '').strip()
    text = text.replace(' Cr', '').replace(' Lakh', '').replace(' L', '')
    # take first number if range like '2,400 / 1,800'
    text = text.split('/')[0].strip()
    try:
        return float(text)
    except ValueError:
        return None


def fetch_screener_data(symbol: str) -> dict:
    """
    Fetch and parse the Screener.in consolidated page for a symbol.
    Returns a dict of {db_column: value} or raises on network/parse error.
    """
    url = BASE_URL.format(symbol=symbol)
    resp = requests.get(url, headers=HEADERS, timeout=15)

    # Screener redirects to standalone if no consolidated; follow it
    if resp.status_code == 404:
        url = f"https://www.screener.in/company/{symbol}/"
        resp = requests.get(url, headers=HEADERS, timeout=15)

    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, 'lxml')
    result = {
        'screener_url': resp.url,
        'source': 'screener',
    }

    # ── Top ratios section ─────────────────────────────────────────────────────
    # Screener renders ratios as <li> items with <span class="name"> and <span class="number">
    for li in soup.select('#top-ratios li'):
        name_el = li.select_one('.name')
        value_el = li.select_one('.number')
        if not name_el or not value_el:
            continue
        label = name_el.get_text(strip=True)
        raw   = value_el.get_text(strip=True)
        col   = RATIO_MAP.get(label)
        if col:
            result[col] = _parse_number(raw)

    # ── Promoter shareholding from the holdings table ─────────────────────────
    # Look for the most recent quarterly promoter % in the shareholding section
    if 'promoter_holding_pct' not in result:
        for row in soup.select('table.data-table tr'):
            cells = row.find_all(['td', 'th'])
            if cells and 'Promoter' in cells[0].get_text():
                # last non-empty cell is the most recent quarter
                for cell in reversed(cells[1:]):
                    val = _parse_number(cell.get_text(strip=True))
                    if val is not None:
                        result['promoter_holding_pct'] = val
                        break
                break

    # ── P&L TTM rows ──────────────────────────────────────────────────────────
    # Revenue and Net Profit from the compact P&L table (first column = TTM)
    for row in soup.select('#profit-loss tr'):
        cells = row.find_all(['td', 'th'])
        if not cells:
            continue
        label = cells[0].get_text(strip=True)
        if 'Sales' in label or 'Revenue' in label:
            val = _parse_number(cells[1].get_text(strip=True)) if len(cells) > 1 else None
            result['revenue_ttm'] = val
        elif 'Net Profit' in label:
            val = _parse_number(cells[1].get_text(strip=True)) if len(cells) > 1 else None
            result['net_profit_ttm'] = val
        elif 'Operating Profit' in label:
            val = _parse_number(cells[1].get_text(strip=True)) if len(cells) > 1 else None
            result['operating_profit_ttm'] = val

    return result


def upsert_fundamentals(stock_id: int, symbol: str, data: dict) -> bool:
    """Upsert one row into fundamentals for today's date."""
    today = date.today()

    # Build dynamic SET clause from non-None values only
    col_map = {k: v for k, v in data.items()
               if k not in ('source', 'screener_url') and v is not None}

    if not col_map:
        print(f"  ⚠ {symbol}: no numeric data parsed")
        return False

    set_clause = ", ".join(f"{col} = EXCLUDED.{col}" for col in col_map)
    set_clause += ", source = EXCLUDED.source, screener_url = EXCLUDED.screener_url"

    columns = list(col_map.keys()) + ['source', 'screener_url']
    values  = list(col_map.values()) + [data.get('source'), data.get('screener_url')]

    col_str = "stock_id, date, " + ", ".join(columns)
    val_str = "%s, %s, " + ", ".join(["%s"] * len(columns))

    sql = f"""
        INSERT INTO fundamentals ({col_str})
        VALUES ({val_str})
        ON CONFLICT (stock_id, date) DO UPDATE SET {set_clause}
    """

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(sql, [stock_id, today] + values)
    conn.commit()
    cursor.close()
    conn.close()
    return True


def collect_screener_fundamentals(watchlist_name='Default', delay=2.0):
    """
    Main entry point. Iterates watchlist, fetches Screener.in, upserts fundamentals.
    Respects a delay between requests to avoid rate limiting.
    """
    stocks = get_watchlist_stocks(watchlist_name)

    print(f"\n{'='*60}")
    print("SCREENER.IN FUNDAMENTALS COLLECTOR")
    print(f"{'='*60}")
    print(f"Stocks: {len(stocks)}  |  Delay: {delay}s between requests\n")

    with refresh_log('screener') as log:
        success = 0
        for stock_id, _, symbol, name in stocks:
            print(f"{symbol} ({name}):")
            try:
                data  = fetch_screener_data(symbol)
                saved = upsert_fundamentals(stock_id, symbol, data)
                if saved:
                    pe   = data.get('pe_ratio', '—')
                    roe  = data.get('roe', '—')
                    prom = data.get('promoter_holding_pct', '—')
                    print(f"  ✓  P/E={pe}  ROE={roe}%  Promoter={prom}%")
                    success += 1
                else:
                    print(f"  ⚠ Skipped (no data)")
            except requests.HTTPError as e:
                print(f"  ✗ HTTP {e.response.status_code} — {symbol} may not exist on Screener")
            except Exception as e:
                print(f"  ✗ Error: {e}")

            time.sleep(delay)

        log['rows'] = success

    print(f"\n{'='*60}")
    print(f"✓ Screener collection complete: {success}/{len(stocks)} stocks updated")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    collect_screener_fundamentals()
