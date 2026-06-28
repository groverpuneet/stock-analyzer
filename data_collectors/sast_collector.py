"""
data_collectors/sast_collector.py
Weekly refresh — Sunday (nse_weekly group)

Fetches SAST (Substantial Acquisition of Shares and Takeovers) disclosures from NSE.
Uses Playwright for JS rendering.

Usage:
    python data_collectors/sast_collector.py
    python data_collectors/sast_collector.py --days 180
"""
import os
import sys
import re
import time
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import get_conn, refresh_log
from utils.logger import get_logger

log = get_logger(__name__)

NSE_SAST_URL = "https://www.nseindia.com/companies-listing/corporate-filings-sast"


def _parse_date(text: str):
    """Parse date from various formats."""
    if not text:
        return None
    text = text.strip()
    for fmt in ['%d-%b-%Y', '%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d']:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_number(text: str):
    """Parse number from text."""
    if not text:
        return None
    text = text.replace(',', '').strip()
    try:
        return float(text)
    except ValueError:
        return None


def _determine_acquirer_type(acquirer_name: str) -> str:
    """Guess acquirer type from name."""
    name_lower = acquirer_name.lower() if acquirer_name else ''

    if any(x in name_lower for x in ['promoter', 'director', 'chairman', 'managing']):
        return 'PROMOTER'
    elif any(x in name_lower for x in ['fii', 'fpi', 'foreign', 'mauritius', 'singapore fund', 'capital group']):
        return 'FII'
    elif any(x in name_lower for x in ['mutual fund', 'insurance', 'lic', 'sbi ', 'hdfc ', 'icici ']):
        return 'DII'
    elif any(x in name_lower for x in ['limited', 'ltd', 'pvt', 'private', 'inc', 'corp', 'llp']):
        return 'COMPANY'
    else:
        return 'INDIVIDUAL'


def fetch_sast_disclosures(days: int = 30) -> list:
    """
    Fetch SAST disclosures from NSE using Playwright.
    Returns list of disclosure dicts.
    """
    from playwright.sync_api import sync_playwright

    disclosures = []
    cutoff_date = date.today() - timedelta(days=days)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            ignore_https_errors=True,
        )
        page = context.new_page()

        try:
            log.info(f"Loading NSE SAST page...")
            page.goto(NSE_SAST_URL, timeout=60000, wait_until='networkidle')
            time.sleep(3)

            # NSE pages load data via API - we need to intercept or parse the rendered table
            # Look for the data table
            table = page.query_selector('table, .data-table, #sastTable')

            if not table:
                # Try waiting for table to appear
                page.wait_for_selector('table', timeout=15000)
                table = page.query_selector('table')

            if table:
                rows = table.query_selector_all('tr')
                log.info(f"Found {len(rows)} rows in SAST table")

                for row in rows[1:]:  # Skip header
                    cells = row.query_selector_all('td')
                    if len(cells) < 5:
                        continue

                    cell_texts = [c.inner_text().strip() for c in cells]

                    # Expected columns: Symbol, Company, Acquirer, Shares, %, Date
                    # Actual structure may vary
                    try:
                        symbol = cell_texts[0] if cell_texts else None
                        acquirer = cell_texts[2] if len(cell_texts) > 2 else None
                        shares_text = cell_texts[3] if len(cell_texts) > 3 else None
                        pct_text = cell_texts[4] if len(cell_texts) > 4 else None
                        date_text = cell_texts[-1] if cell_texts else None

                        disc_date = _parse_date(date_text)
                        if disc_date and disc_date < cutoff_date:
                            continue

                        disclosures.append({
                            'symbol': symbol,
                            'acquirer_name': acquirer,
                            'acquirer_type': _determine_acquirer_type(acquirer),
                            'shares_acquired': int(_parse_number(shares_text)) if shares_text else None,
                            'pct_acquired': _parse_number(pct_text),
                            'disclosure_date': disc_date or date.today(),
                            'transaction_type': 'ACQUISITION',
                            'source': 'nse_sast',
                        })
                    except Exception as e:
                        log.warning(f"Failed to parse row: {e}")
                        continue

            else:
                log.warning("No SAST table found on page")

                # Try to get data from page API calls
                # NSE often loads data via XHR
                # Check if there's data in the page content
                content = page.content()
                if 'No records' in content or 'No data' in content:
                    log.info("No SAST records available")

        except Exception as e:
            log.error(f"SAST fetch failed: {e}")
        finally:
            browser.close()

    return disclosures


def fetch_sast_from_api(days: int = 30) -> list:
    """
    Fetch SAST-related disclosures from NSE corporate announcements API.
    Filters for acquisition/SAST-related announcements.
    """
    import requests
    import time

    disclosures = []
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Referer': 'https://www.nseindia.com/',
    })

    # Keywords to identify SAST/acquisition announcements
    SAST_KEYWORDS = [
        'sast', 'acquisition', 'substantial', 'takeover',
        'reg 29', 'regulation 29', 'reg 30', 'regulation 30',
        'open offer', 'shares acquired', 'stake acquired'
    ]

    try:
        # Warm up session - get cookies
        log.info("Warming up NSE session...")
        session.get('https://www.nseindia.com', timeout=10)
        time.sleep(1)

        # Use corporate announcements API and filter for SAST-related
        from_date = (date.today() - timedelta(days=days)).strftime('%d-%m-%Y')
        to_date = date.today().strftime('%d-%m-%Y')

        url = f"https://www.nseindia.com/api/corporate-announcements?index=equities&from_date={from_date}&to_date={to_date}"
        log.info(f"Fetching corporate announcements...")
        resp = session.get(url, timeout=30)

        if resp.status_code == 200:
            data = resp.json()
            log.info(f"Got {len(data)} total announcements, filtering for SAST...")

            for item in data:
                desc = (item.get('desc') or '').lower()
                subject = (item.get('subject') or '').lower()
                combined = desc + ' ' + subject

                if any(kw in combined for kw in SAST_KEYWORDS):
                    disclosures.append({
                        'symbol': item.get('symbol'),
                        'acquirer_name': item.get('desc', '')[:200],  # Use desc as acquirer info
                        'acquirer_type': _determine_acquirer_type(item.get('desc', '')),
                        'shares_acquired': None,  # Not directly available
                        'pct_acquired': None,
                        'total_holding_pct': None,
                        'acquisition_date': _parse_date(item.get('an_dt')),
                        'disclosure_date': _parse_date(item.get('dt')) or _parse_date(item.get('an_dt')) or date.today(),
                        'transaction_type': 'ACQUISITION',
                        'source': 'nse_announcements',
                    })
        else:
            log.warning(f"API returned status {resp.status_code}")

    except Exception as e:
        log.warning(f"NSE API failed: {e}")

    return disclosures


def store_sast_disclosures(disclosures: list) -> int:
    """Store SAST disclosures. Returns count stored."""
    if not disclosures:
        return 0

    conn = get_conn()
    cursor = conn.cursor()

    # Build symbol -> stock_id map
    cursor.execute("SELECT tradingsymbol, id FROM stocks WHERE market = 'NSE'")
    symbol_map = {row[0]: row[1] for row in cursor.fetchall()}

    count = 0
    for disc in disclosures:
        try:
            stock_id = symbol_map.get(disc['symbol'])

            cursor.execute("""
                INSERT INTO sast_disclosures
                    (stock_id, symbol, acquirer_name, acquirer_type,
                     shares_acquired, pct_acquired, total_holding_pct,
                     acquisition_date, disclosure_date, transaction_type, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                stock_id, disc['symbol'], disc['acquirer_name'], disc['acquirer_type'],
                disc.get('shares_acquired'), disc.get('pct_acquired'), disc.get('total_holding_pct'),
                disc.get('acquisition_date'), disc['disclosure_date'],
                disc.get('transaction_type'), disc['source']
            ))
            count += 1
        except Exception as e:
            log.error(f"Store SAST failed: {e}")

    conn.commit()
    cursor.close()
    conn.close()
    return count


def collect_sast_disclosures(days: int = 30):
    """
    Collect SAST disclosures from NSE.
    """
    print(f"\n{'='*60}")
    print("SAST DISCLOSURES COLLECTOR")
    print(f"{'='*60}")
    print(f"Looking back {days} days\n")

    with refresh_log('sast_disclosures') as rlog:
        # Try API first (faster, more reliable)
        disclosures = fetch_sast_from_api(days)

        if not disclosures:
            log.info("API returned no data, trying Playwright...")
            disclosures = fetch_sast_disclosures(days)

        log.info(f"Found {len(disclosures)} SAST disclosures")

        if disclosures:
            # Print sample
            for d in disclosures[:10]:
                print(f"  {d['symbol']}: {d['acquirer_name'][:30]}... — {d.get('pct_acquired', '?')}% ({d['acquirer_type']})")

        count = store_sast_disclosures(disclosures)
        rlog['rows'] = count

    print(f"\n{'='*60}")
    print(f"✓ SAST collection complete: {count} disclosures stored")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=int, default=30, help='Days to look back')
    args = parser.parse_args()

    collect_sast_disclosures(days=args.days)
