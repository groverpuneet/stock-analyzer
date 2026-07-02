"""
data_collectors/fii_dii_collector.py
Daily refresh — 4:30 PM IST (after NSE publishes the day's activity report)

NSE publishes FII/DII daily activity as a CSV/JSON on their website.
We fall back to a secondary scrape if the primary endpoint fails.

Usage:
    python data_collectors/fii_dii_collector.py
"""
import requests
from bs4 import BeautifulSoup
import psycopg2
import sys
import os
from datetime import date, datetime, timedelta
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.db import get_conn, refresh_log

NSE_BASE     = "https://www.nseindia.com"
NSE_FII_URL  = "https://www.nseindia.com/api/fiidiiTradeReact"   # returns JSON

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://www.nseindia.com/',
}

# Fallback: Moneycontrol / NSE HTML page scrape
MC_FII_URL = "https://www.moneycontrol.com/stocks/marketstats/fii_dii_activity/index.php"


def get_nse_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        session.get(NSE_BASE, timeout=10)
    except Exception:
        pass
    return session


def _parse_cr(value) -> float:
    """Parse crore values like '12,345.67' or '-2345.00' to float."""
    if value is None:
        return None
    try:
        return float(str(value).replace(',', '').strip())
    except (ValueError, AttributeError):
        return None


def fetch_from_nse(session: requests.Session) -> list:
    """
    Fetch FII/DII data from NSE API.

    The API returns ONE item per category per day:
        {"buyValue": "...", "category": "FII/FPI *" | "DII *", "date": "25-Jun-2026",
         "netValue": "...", "sellValue": "..."}
    We group by date and merge the FII and DII rows into one record.
    """
    resp = session.get(NSE_FII_URL, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    by_date: dict = {}
    for item in data:
        d = _parse_nse_date(item.get('date') or item.get('Date'))
        if not d:
            continue
        cat = (item.get('category') or '').upper()
        bucket = "FII" if ("FII" in cat or "FPI" in cat) else ("DII" if "DII" in cat else cat)
        by_date.setdefault(d, {})[bucket] = item

    results = []
    for d, cats in by_date.items():
        fii, dii = cats.get("FII"), cats.get("DII")
        row = {
            'date':     d,
            'fii_buy':  _parse_cr(fii.get('buyValue')) if fii else None,
            'fii_sell': _parse_cr(fii.get('sellValue')) if fii else None,
            'fii_net':  _parse_cr(fii.get('netValue')) if fii else None,
            'dii_buy':  _parse_cr(dii.get('buyValue')) if dii else None,
            'dii_sell': _parse_cr(dii.get('sellValue')) if dii else None,
            'dii_net':  _parse_cr(dii.get('netValue')) if dii else None,
            'source':   'nse',
        }
        if row['fii_net'] is None and row['fii_buy'] is not None and row['fii_sell'] is not None:
            row['fii_net'] = round(row['fii_buy'] - row['fii_sell'], 2)
        if row['dii_net'] is None and row['dii_buy'] is not None and row['dii_sell'] is not None:
            row['dii_net'] = round(row['dii_buy'] - row['dii_sell'], 2)
        results.append(row)

    return results


def fetch_from_moneycontrol() -> list:
    """Fallback scraper for FII/DII from Moneycontrol."""
    resp = requests.get(MC_FII_URL, headers={'User-Agent': HEADERS['User-Agent']}, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, 'lxml')
    results = []

    # Moneycontrol table structure may change; this targets the main data table
    table = soup.find('table', {'id': 'fiiTable'}) or soup.find('table', class_=re.compile(r'fii', re.I))
    if not table:
        return results

    rows = table.find_all('tr')[1:]  # skip header
    for row in rows:
        cells = [td.get_text(strip=True) for td in row.find_all('td')]
        if len(cells) < 7:
            continue
        try:
            parsed_date = _parse_nse_date(cells[0])
            if not parsed_date:
                continue
            results.append({
                'date':     parsed_date,
                'fii_buy':  _parse_cr(cells[1]),
                'fii_sell': _parse_cr(cells[2]),
                'fii_net':  _parse_cr(cells[3]),
                'dii_buy':  _parse_cr(cells[4]),
                'dii_sell': _parse_cr(cells[5]),
                'dii_net':  _parse_cr(cells[6]),
                'source':   'moneycontrol',
            })
        except Exception:
            continue

    return results


NIFTYTRADER_URL = "https://webapi.niftytrader.in/webapi/Resource/fii-dii-activity-data"


def fetch_from_niftytrader() -> list:
    """History source (~30 trading days) of FII/DII *net* cash flows.

    NSE's fiidiiTradeReact API only returns the latest day, so this backfills the
    30-day window the Macro chart needs. Net values match NSE to the paisa; buy/sell
    breakdown isn't provided (left NULL — the daily NSE run fills those for today).
    """
    import time
    hdrs = {'User-Agent': HEADERS['User-Agent'], 'Accept': 'application/json'}
    last_err = None
    for attempt in range(4):
        try:
            resp = requests.get(NIFTYTRADER_URL, headers=hdrs, timeout=30)
            resp.raise_for_status()
            break
        except Exception as e:  # noqa: BLE001 — endpoint is occasionally slow
            last_err = e
            time.sleep(3 * (attempt + 1))
    else:
        raise RuntimeError(f"niftytrader unreachable after retries: {last_err}")
    data = (resp.json().get('resultData') or {}).get('fii_dii_data') or []
    results = []
    for item in data:
        d = _parse_nse_date(str(item.get('created_at', ''))[:10])
        if not d:
            continue
        results.append({
            'date':     d,
            'fii_buy':  None, 'fii_sell': None,
            'fii_net':  _parse_cr(item.get('fii_net_value')),
            'dii_buy':  None, 'dii_sell': None,
            'dii_net':  _parse_cr(item.get('dii_net_value')),
            'source':   'niftytrader',
        })
    return results


def store_fii_dii_net(rows: list[dict]) -> int:
    """Upsert net-only history without clobbering richer same-day rows (NSE buy/sell)."""
    conn = get_conn(); cursor = conn.cursor(); count = 0
    for row in rows:
        try:
            cursor.execute("""
                INSERT INTO fii_dii_flows (date, fii_net, dii_net, source)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (date) DO UPDATE SET
                    fii_net = COALESCE(fii_dii_flows.fii_net, EXCLUDED.fii_net),
                    dii_net = COALESCE(fii_dii_flows.dii_net, EXCLUDED.dii_net),
                    source  = COALESCE(fii_dii_flows.source, EXCLUDED.source)
            """, (row['date'], row['fii_net'], row['dii_net'], row['source']))
            count += 1
        except Exception as e:
            print(f"  ⚠ Row insert error ({row.get('date')}): {e}")
    conn.commit(); cursor.close(); conn.close()
    return count


def backfill_fii_dii_history() -> int:
    """One-shot 30-day backfill from niftytrader. Returns rows upserted."""
    rows = fetch_from_niftytrader()
    n = store_fii_dii_net(rows)
    print(f"  ✓ niftytrader backfill: {n} days upserted")
    return n


def _parse_nse_date(raw) -> date:
    if not raw:
        return None
    for fmt in ('%d-%b-%Y', '%d-%m-%Y', '%Y-%m-%d', '%b %d, %Y', '%d/%m/%Y'):
        try:
            return datetime.strptime(str(raw).strip(), fmt).date()
        except ValueError:
            continue
    return None


def store_fii_dii(rows: list[dict]) -> int:
    """Upsert FII/DII rows. Returns count stored."""
    conn   = get_conn()
    cursor = conn.cursor()
    count  = 0

    for row in rows:
        try:
            cursor.execute("""
                INSERT INTO fii_dii_flows
                    (date, fii_buy, fii_sell, fii_net, dii_buy, dii_sell, dii_net, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (date) DO UPDATE SET
                    fii_buy  = EXCLUDED.fii_buy,
                    fii_sell = EXCLUDED.fii_sell,
                    fii_net  = EXCLUDED.fii_net,
                    dii_buy  = EXCLUDED.dii_buy,
                    dii_sell = EXCLUDED.dii_sell,
                    dii_net  = EXCLUDED.dii_net,
                    source   = EXCLUDED.source
            """, (
                row['date'], row['fii_buy'], row['fii_sell'], row['fii_net'],
                row['dii_buy'], row['dii_sell'], row['dii_net'], row['source']
            ))
            count += 1
        except Exception as e:
            print(f"  ⚠ Row insert error ({row.get('date')}): {e}")

    conn.commit()
    cursor.close()
    conn.close()
    return count


def collect_fii_dii():
    print(f"\n{'='*60}")
    print("FII / DII FLOWS COLLECTOR")
    print(f"{'='*60}")

    with refresh_log('fii_dii') as log:
        rows = []

        # Try NSE primary
        try:
            session = get_nse_session()
            rows = fetch_from_nse(session)
            print(f"  ✓ NSE API: {len(rows)} days fetched")
        except Exception as e:
            print(f"  ⚨ NSE API failed ({e}), trying Moneycontrol fallback...")
            try:
                rows = fetch_from_moneycontrol()
                print(f"  ✓ Moneycontrol fallback: {len(rows)} days fetched")
            except Exception as e2:
                raise RuntimeError(f"Both sources failed. NSE: {e} | MC: {e2}")

        n = store_fii_dii(rows)

        # Top up the 30-day history window (net-only) so the Macro chart stays full.
        try:
            n += backfill_fii_dii_history()
        except Exception as e:
            print(f"  ⚨ niftytrader history top-up failed ({e})")

        log['rows'] = n

    # Print last 5 days
    _print_recent(5)

    print(f"\n{'='*60}")
    print(f"✓ FII/DII collection complete: {n} rows upserted")
    print(f"{'='*60}\n")


def _print_recent(days=5):
    conn   = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT date, fii_net, dii_net
        FROM fii_dii_flows
        ORDER BY date DESC
        LIMIT %s
    """, (days,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if not rows:
        return

    print(f"\n  Recent FII/DII flows (₹ Cr):")
    print(f"  {'Date':<14} {'FII Net':>12} {'DII Net':>12} {'Combined':>12}")
    print(f"  {'-'*52}")
    for dt, fii, dii in rows:
        fii  = fii  or 0
        dii  = dii  or 0
        icon = '🟢' if (fii + dii) > 0 else '🔴'
        print(f"  {str(dt):<14} {fii:>12,.0f} {dii:>12,.0f} {icon} {fii+dii:>9,.0f}")


if __name__ == "__main__":
    if "--backfill" in sys.argv:
        backfill_fii_dii_history()
        _print_recent(30)
    else:
        collect_fii_dii()
