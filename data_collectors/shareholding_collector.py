"""
data_collectors/shareholding_collector.py

Collects quarterly shareholding pattern data from Screener.in for all watchlist stocks.
Fields: promoter %, FII %, DII %, government %, public %, no. of shareholders

Source: Screener.in (aggregates from NSE/BSE quarterly SEBI filings)
Schedule: Weekly Sunday (checks for new quarters, inserts only when new data appears)
Table: shareholding_pattern

Lag note: NSE-listed companies must file shareholding within 21 days of quarter end.
  - Q4 FY26 (Jan–Mar 2026) data available ~Apr 21, 2026
  - Q1 FY27 (Apr–Jun 2026) data available ~Jul 21, 2026
Collector gracefully skips if the current quarter isn't filed yet.
"""
import os
import sys
import logging
import calendar
import time
from datetime import date, timedelta

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.db import get_conn, refresh_log, get_watchlist_stocks

log = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml',
    'Accept-Language': 'en-US,en;q=0.5',
}

MONTH_MAP = {m: i for i, m in enumerate(
    ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], 1
)}

REQUEST_DELAY = 2.5  # seconds between stock fetches


def _parse_quarter_end(label: str):
    """'Jun 2023' → date(2023, 6, 30)"""
    parts = label.strip().split()
    if len(parts) != 2:
        return None
    mon = MONTH_MAP.get(parts[0])
    if not mon:
        return None
    try:
        year = int(parts[1])
        last_day = calendar.monthrange(year, mon)[1]
        return date(year, mon, last_day)
    except (ValueError, TypeError):
        return None


def _pct(s: str):
    try:
        return float(s.replace('%', '').replace(',', '').strip())
    except (ValueError, AttributeError):
        return None


def _int_val(s: str):
    try:
        return int(s.replace(',', '').strip())
    except (ValueError, AttributeError):
        return None


def _fetch_screener(symbol: str) -> list[dict]:
    """
    Fetch shareholding pattern quarters for a symbol from Screener.in.
    Returns list of dicts ordered oldest → newest.
    Returns [] if the page is not found or shareholding section is absent.
    """
    for url in [
        f'https://www.screener.in/company/{symbol}/consolidated/',
        f'https://www.screener.in/company/{symbol}/',
    ]:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
        except requests.RequestException as e:
            log.warning(f"{symbol}: request failed — {e}")
            return []
        if resp.status_code == 404:
            continue
        if resp.status_code != 200:
            log.warning(f"{symbol}: HTTP {resp.status_code}")
            return []

        soup = BeautifulSoup(resp.text, 'lxml')

        for section in soup.find_all(['section', 'div'], class_=True):
            heading = section.find(['h2', 'h3', 'h4'])
            if not (heading and 'holding' in heading.get_text().lower()):
                continue
            table = section.find('table')
            if not table:
                continue
            rows = table.find_all('tr')
            if not rows:
                continue

            quarters = [td.get_text().strip() for td in rows[0].find_all(['th', 'td'])][1:]
            data: dict[str, list] = {}

            for row in rows[1:]:
                cells = [td.get_text().strip() for td in row.find_all(['th', 'td'])]
                if not cells:
                    continue
                label = cells[0].replace('\xa0', '').replace('+', '').strip().lower()
                vals = cells[1:]
                if 'promoter' in label:
                    data['promoter'] = vals
                elif 'fii' in label or 'foreign' in label:
                    data['fii'] = vals
                elif 'dii' in label or 'domestic' in label:
                    data['dii'] = vals
                elif 'government' in label:
                    data['government'] = vals
                elif 'public' in label:
                    data['public'] = vals
                elif 'shareholder' in label:
                    data['shareholders'] = vals

            records = []
            for i, q_label in enumerate(quarters):
                qdate = _parse_quarter_end(q_label)
                if not qdate:
                    continue
                def _get(key):
                    v = data.get(key, [])
                    return v[i] if i < len(v) else None

                records.append({
                    'quarter_end':    qdate,
                    'promoter_pct':   _pct(_get('promoter') or ''),
                    'fii_pct':        _pct(_get('fii') or ''),
                    'dii_pct':        _pct(_get('dii') or ''),
                    'government_pct': _pct(_get('government') or ''),
                    'public_pct':     _pct(_get('public') or ''),
                    'num_shareholders': _int_val(_get('shareholders') or ''),
                })
            return records

    log.info(f"{symbol}: shareholding section not found on Screener.in")
    return []


def _get_last_known_quarter(conn, stock_id: int):
    """Return the most recent quarter_end we already have for this stock."""
    cur = conn.cursor()
    cur.execute(
        "SELECT MAX(quarter_end) FROM shareholding_pattern WHERE stock_id = %s",
        (stock_id,)
    )
    result = cur.fetchone()[0]
    cur.close()
    return result


def collect_shareholding(watchlist_name: str = 'Default') -> dict:
    """
    Collect shareholding pattern for all stocks in watchlist_name.
    Upserts all available quarters from Screener.in.
    Returns {'rows_inserted': int, 'rows_updated': int, 'stocks_checked': int}.
    """
    stocks = get_watchlist_stocks(watchlist_name)
    if not stocks:
        log.warning(f"No stocks in watchlist '{watchlist_name}'")
        return {'rows_inserted': 0, 'rows_updated': 0, 'stocks_checked': 0}

    today = date.today()
    total_inserted = 0
    total_updated = 0

    with refresh_log('shareholding_pattern') as meta:
        conn = get_conn()
        cur = conn.cursor()

        for stock_id, _, symbol, name in stocks:
            log.info(f"Fetching shareholding for {symbol} ({name[:30]})")

            records = _fetch_screener(symbol)
            if not records:
                log.info(f"  {symbol}: no data available")
                time.sleep(REQUEST_DELAY)
                continue

            last_known = _get_last_known_quarter(conn, stock_id)
            new_quarters = [r for r in records if r['quarter_end'] > (last_known or date.min)]

            if not new_quarters:
                log.info(f"  {symbol}: {len(records)} quarters already up to date (latest: {records[-1]['quarter_end']})")
                time.sleep(REQUEST_DELAY)
                continue

            log.info(f"  {symbol}: {len(new_quarters)} new quarters to insert (latest: {records[-1]['quarter_end']})")

            for rec in records:
                cur.execute("""
                    INSERT INTO shareholding_pattern
                        (stock_id, symbol, quarter_end,
                         promoter_pct, fii_pct, dii_pct, government_pct, public_pct,
                         num_shareholders, source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'screener')
                    ON CONFLICT (stock_id, quarter_end) DO UPDATE SET
                        promoter_pct    = EXCLUDED.promoter_pct,
                        fii_pct         = EXCLUDED.fii_pct,
                        dii_pct         = EXCLUDED.dii_pct,
                        government_pct  = EXCLUDED.government_pct,
                        public_pct      = EXCLUDED.public_pct,
                        num_shareholders = EXCLUDED.num_shareholders,
                        source          = EXCLUDED.source
                """, (
                    stock_id, symbol, rec['quarter_end'],
                    rec['promoter_pct'], rec['fii_pct'], rec['dii_pct'],
                    rec['government_pct'], rec['public_pct'],
                    rec['num_shareholders'],
                ))
                if cur.rowcount == 1 and rec['quarter_end'] > (last_known or date.min):
                    total_inserted += 1
                else:
                    total_updated += 1

            conn.commit()
            time.sleep(REQUEST_DELAY)

        cur.close()
        conn.close()

        total_rows = total_inserted + total_updated
        meta['rows'] = total_rows

    log.info(
        f"Shareholding done: {total_inserted} new rows, {total_updated} updated, "
        f"{len(stocks)} stocks checked"
    )
    return {
        'rows_inserted':   total_inserted,
        'rows_updated':    total_updated,
        'stocks_checked':  len(stocks),
    }


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    result = collect_shareholding()
    print(f"Done: {result}")
