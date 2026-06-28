"""
data_collectors/analyst_targets_collector.py
Weekly refresh — Sunday (nse_weekly group)

Fetches analyst consensus ratings and price targets from Tickertape.in.
Uses Playwright for JS rendering.

Usage:
    python data_collectors/analyst_targets_collector.py
    python data_collectors/analyst_targets_collector.py --symbol RELIANCE
"""
import os
import sys
import re
import time
from datetime import datetime, date
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import get_conn, refresh_log, get_watchlist_stocks
from utils.logger import get_logger

log = get_logger(__name__)

TICKERTAPE_URL = "https://www.tickertape.in/stocks/{symbol}/forecasts"

# Tickertape uses company slug, not trading symbol
# Format: company-name-TICKER (4-letter code)
SYMBOL_TO_SLUG = {
    'RELIANCE': 'reliance-industries-RELI',
    'TCS': 'tata-consultancy-services-TCS',
    'HDFCBANK': 'hdfc-bank-HDBK',
    'INFY': 'infosys-INFY',
    'ICICIBANK': 'icici-bank-ICBK',
    'SBIN': 'state-bank-of-india-SBIN',
    'BHARTIARTL': 'bharti-airtel-BRTI',
    'ITC': 'itc-ITC',
    'KOTAKBANK': 'kotak-mahindra-bank-KTKM',
    'WIPRO': 'wipro-WIPR',
    'AXISBANK': 'axis-bank-AXBK',
    'ASIANPAINT': 'asian-paints-ASPN',
    'BAJFINANCE': 'bajaj-finance-BJFN',
    'HINDUNILVR': 'hindustan-unilever-HLL',
    'TITAN': 'titan-company-TITN',
    'TATASTEEL': 'tata-steel-TATA',
    'NTPC': 'ntpc-NTPC',
    'POWERGRID': 'power-grid-corporation-of-india-PGRD',
    'TATACHEM': 'tata-chemicals-TTCH',
    'CIPLA': 'cipla-CIPL',
    'BAJAJFINSV': 'bajaj-finserv-BJFS',
    'DABUR': 'dabur-india-DABU',
    'NESTLEIND': 'nestle-india-NEST',
    'DMART': 'avenue-supermarts-DMAR',
    'ETERNAL': 'zomato-ZOMT',
}


def _parse_number(text: str):
    """Parse number from text like '₹1,234.56' or '12.34%' or '1,234'."""
    if not text:
        return None
    text = text.replace('₹', '').replace(',', '').replace('%', '').strip()
    try:
        return float(text)
    except ValueError:
        return None


def _determine_consensus(buy: int, hold: int, sell: int) -> str:
    """Determine consensus rating from counts."""
    total = (buy or 0) + (hold or 0) + (sell or 0)
    if total == 0:
        return None

    buy_pct = (buy or 0) / total * 100
    sell_pct = (sell or 0) / total * 100

    if buy_pct >= 70:
        return 'STRONG_BUY'
    elif buy_pct >= 50:
        return 'BUY'
    elif sell_pct >= 70:
        return 'STRONG_SELL'
    elif sell_pct >= 50:
        return 'SELL'
    else:
        return 'HOLD'


def fetch_analyst_data_tickertape(symbol: str) -> dict:
    """
    Fetch analyst data from Tickertape using Playwright.
    Returns dict with analyst counts, targets, consensus.
    """
    from playwright.sync_api import sync_playwright

    # Get slug for symbol or try symbol directly
    slug = SYMBOL_TO_SLUG.get(symbol, symbol.lower())
    url = f"https://www.tickertape.in/stocks/{slug}/forecasts"

    result = {
        'analyst_count': None,
        'buy_count': None,
        'hold_count': None,
        'sell_count': None,
        'avg_target_price': None,
        'high_target': None,
        'low_target': None,
        'current_price': None,
        'source': 'tickertape',
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            ignore_https_errors=True,
        )
        page = context.new_page()

        try:
            page.goto(url, timeout=30000, wait_until='networkidle')
            time.sleep(2)  # Let dynamic content load

            page_text = page.inner_text('body')

            # Parse analyst count from "from X analysts" pattern
            analyst_count_match = re.search(r'from\s+(\d+)\s+analysts?', page_text, re.I)
            if analyst_count_match:
                result['analyst_count'] = int(analyst_count_match.group(1))

            # Parse Strong Buy / Buy / Hold / Sell counts
            # Tickertape shows these in a rating distribution
            strong_buy = re.search(r'(\d+)\s*Strong\s*Buy', page_text, re.I)
            buy_match = re.search(r'(?<!Strong\s)(\d+)\s*Buy(?!\s*Strong)', page_text, re.I)
            hold_match = re.search(r'(\d+)\s*Hold', page_text, re.I)
            sell_match = re.search(r'(?<!Strong\s)(\d+)\s*Sell(?!\s*Strong)', page_text, re.I)
            strong_sell = re.search(r'(\d+)\s*Strong\s*Sell', page_text, re.I)

            # Combine strong buy + buy into buy_count
            buy_total = 0
            if strong_buy:
                buy_total += int(strong_buy.group(1))
            if buy_match:
                buy_total += int(buy_match.group(1))
            if buy_total > 0:
                result['buy_count'] = buy_total

            if hold_match:
                result['hold_count'] = int(hold_match.group(1))

            # Combine strong sell + sell into sell_count
            sell_total = 0
            if strong_sell:
                sell_total += int(strong_sell.group(1))
            if sell_match:
                sell_total += int(sell_match.group(1))
            if sell_total > 0:
                result['sell_count'] = sell_total

            # Calculate analyst_count if not found directly
            if not result['analyst_count'] and any([result['buy_count'], result['hold_count'], result['sell_count']]):
                result['analyst_count'] = (result['buy_count'] or 0) + (result['hold_count'] or 0) + (result['sell_count'] or 0)

            # Parse target price
            target_match = re.search(r'(?:Target|Avg\.?\s*Target|Consensus)[:\s]*₹?\s*([\d,]+(?:\.\d+)?)', page_text, re.I)
            if target_match:
                result['avg_target_price'] = _parse_number(target_match.group(1))

            # Parse current price
            price_match = re.search(r'(?:Current|Price|LTP)[:\s]*₹?\s*([\d,]+(?:\.\d+)?)', page_text, re.I)
            if price_match:
                result['current_price'] = _parse_number(price_match.group(1))

        except Exception as e:
            log.warning(f"Tickertape fetch failed for {symbol}: {e}")
        finally:
            browser.close()

    return result


def fetch_analyst_data_screener(symbol: str) -> dict:
    """
    Fallback: Fetch analyst estimates from Screener.in.
    """
    import requests
    from bs4 import BeautifulSoup

    result = {
        'analyst_count': None,
        'buy_count': None,
        'hold_count': None,
        'sell_count': None,
        'avg_target_price': None,
        'high_target': None,
        'low_target': None,
        'current_price': None,
        'source': 'screener',
    }

    url = f"https://www.screener.in/company/{symbol}/consolidated/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    }

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 404:
            url = f"https://www.screener.in/company/{symbol}/"
            resp = requests.get(url, headers=headers, timeout=15)

        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'lxml')

        # Get current price
        for li in soup.select('#top-ratios li'):
            name_el = li.select_one('.name')
            value_el = li.select_one('.number')
            if name_el and value_el and 'Current Price' in name_el.get_text():
                result['current_price'] = _parse_number(value_el.get_text())
                break

        # Screener doesn't have detailed analyst ratings, but may show estimates
        # Look for analyst estimates section
        estimates_section = soup.find(string=re.compile(r'Analyst|Estimates', re.I))
        if estimates_section:
            parent = estimates_section.find_parent('section') or estimates_section.find_parent('div')
            if parent:
                text = parent.get_text()
                target_match = re.search(r'(?:Target|Price)[:\s]*₹?([\d,]+(?:\.\d+)?)', text, re.I)
                if target_match:
                    result['avg_target_price'] = _parse_number(target_match.group(1))

    except Exception as e:
        log.warning(f"Screener fetch failed for {symbol}: {e}")

    return result


def store_analyst_target(stock_id: int, symbol: str, data: dict) -> bool:
    """Store analyst target data."""
    today = date.today()
    now = datetime.now()

    buy = data.get('buy_count') or 0
    hold = data.get('hold_count') or 0
    sell = data.get('sell_count') or 0

    consensus = _determine_consensus(buy, hold, sell)

    # Calculate upside
    upside = None
    if data.get('avg_target_price') and data.get('current_price'):
        upside = round((data['avg_target_price'] - data['current_price']) / data['current_price'] * 100, 2)

    conn = get_conn()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO analyst_targets
                (stock_id, date, analyst_count, buy_count, hold_count, sell_count,
                 avg_target_price, high_target, low_target, current_price,
                 upside_pct, consensus_rating, source, scraped_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (stock_id, date) DO UPDATE SET
                analyst_count = EXCLUDED.analyst_count,
                buy_count = EXCLUDED.buy_count,
                hold_count = EXCLUDED.hold_count,
                sell_count = EXCLUDED.sell_count,
                avg_target_price = EXCLUDED.avg_target_price,
                high_target = EXCLUDED.high_target,
                low_target = EXCLUDED.low_target,
                current_price = EXCLUDED.current_price,
                upside_pct = EXCLUDED.upside_pct,
                consensus_rating = EXCLUDED.consensus_rating,
                source = EXCLUDED.source,
                scraped_at = EXCLUDED.scraped_at
        """, (
            stock_id, today,
            data.get('analyst_count'), data.get('buy_count'), data.get('hold_count'), data.get('sell_count'),
            data.get('avg_target_price'), data.get('high_target'), data.get('low_target'), data.get('current_price'),
            upside, consensus, data.get('source'), now
        ))
        conn.commit()
        return True
    except Exception as e:
        log.error(f"Store failed for {symbol}: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


def collect_analyst_targets(watchlist_name: str = 'Default', symbol: str = None, delay: float = 3.0):
    """
    Collect analyst targets for watchlist stocks.
    """
    print(f"\n{'='*60}")
    print("ANALYST TARGETS COLLECTOR")
    print(f"{'='*60}")

    if symbol:
        # Single stock mode
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM stocks WHERE tradingsymbol = %s", (symbol,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if not row:
            print(f"Stock {symbol} not found")
            return

        stock_id = row[0]
        print(f"Fetching analyst data for {symbol}...")

        data = fetch_analyst_data_tickertape(symbol)
        if not data.get('analyst_count'):
            print(f"  Tickertape failed, trying Screener...")
            data = fetch_analyst_data_screener(symbol)

        if store_analyst_target(stock_id, symbol, data):
            print(f"  ✓ {symbol}: {data.get('analyst_count') or 0} analysts, target ₹{data.get('avg_target_price') or '—'}")
        else:
            print(f"  ✗ {symbol}: no data")
        return

    # Full watchlist mode
    stocks = get_watchlist_stocks(watchlist_name)
    # Filter out MF instruments
    stocks = [(sid, tk, sym, name) for sid, tk, sym, name in stocks if not sym.startswith('INF')]

    print(f"Stocks: {len(stocks)}  |  Delay: {delay}s\n")

    with refresh_log('analyst_targets') as rlog:
        rlog['expected'] = len(stocks)
        success = 0

        for stock_id, _, symbol, name in stocks:
            print(f"{symbol}:")

            data = fetch_analyst_data_tickertape(symbol)
            if not data.get('analyst_count'):
                print(f"  Tickertape: no data, trying Screener...")
                data = fetch_analyst_data_screener(symbol)

            if data.get('analyst_count') or data.get('avg_target_price'):
                if store_analyst_target(stock_id, symbol, data):
                    buy = data.get('buy_count') or 0
                    hold = data.get('hold_count') or 0
                    sell = data.get('sell_count') or 0
                    target = data.get('avg_target_price')
                    print(f"  ✓ {buy}B/{hold}H/{sell}S, target ₹{target or '—'}")
                    success += 1
                else:
                    print(f"  ✗ Store failed")
            else:
                print(f"  — No analyst coverage")

            time.sleep(delay)

        rlog['rows'] = success

    print(f"\n{'='*60}")
    print(f"✓ Analyst targets complete: {success}/{len(stocks)} stocks")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', help='Single stock symbol')
    args = parser.parse_args()

    collect_analyst_targets(symbol=args.symbol)
