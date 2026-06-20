"""
data_collectors/nse_actions_collector.py
Event-driven — checked daily post-market, stores upcoming actions.

Uses NSE's public JSON endpoints (no auth):
  - Corporate actions:  https://www.nseindia.com/api/corporates-corporateActions
  - Earnings calendar:  derived from corporate actions + BSE results date API

Usage:
    python data_collectors/nse_actions_collector.py
"""
import requests
import psycopg2
import sys
import os
import time
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.db import get_conn, refresh_log, get_stock_id_map

# NSE requires a session cookie obtained by hitting the homepage first
NSE_BASE   = "https://www.nseindia.com"
NSE_ACTIONS_URL = (
    "https://www.nseindia.com/api/corporates-corporateActions"
    "?index=equities&from_date={from_date}&to_date={to_date}"
)
NSE_RESULTS_URL = (
    "https://www.nseindia.com/api/event-calendar"
)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                  'Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.nseindia.com/',
}

ACTION_TYPE_MAP = {
    'dividend':       'dividend',
    'div':            'dividend',
    'interim':        'dividend',
    'final':          'dividend',
    'special':        'dividend',
    'split':          'split',
    'face value':     'split',
    'sub-division':   'split',
    'bonus':          'bonus',
    'rights':         'rights',
    'buyback':        'buyback',
    'buy-back':       'buyback',
}


def get_nse_session() -> requests.Session:
    """Create a session with NSE cookie (required for API calls)."""
    session = requests.Session()
    session.headers.update(HEADERS)
    # Hit homepage to get cookies
    try:
        session.get(NSE_BASE, timeout=10)
        time.sleep(1)
    except Exception:
        pass
    return session


def classify_action(subject: str) -> str:
    text = subject.lower()
    for keyword, action_type in ACTION_TYPE_MAP.items():
        if keyword in text:
            return action_type
    return 'other'


def parse_amount(subject: str):
    """Try to extract dividend amount from subject string like 'Rs 5.50 per share'."""
    import re
    match = re.search(r'rs\.?\s*([\d.]+)', subject, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    return None


def parse_ratio(subject: str):
    """Try to extract ratio like '1:2' or '1 for 2' from subject."""
    import re
    match = re.search(r'(\d+)\s*[:/]\s*(\d+)', subject)
    if match:
        return f"{match.group(1)}:{match.group(2)}"
    return None


def fetch_corporate_actions(session: requests.Session, days_ahead=90) -> list:
    """Fetch NSE corporate actions for the next `days_ahead` days."""
    today     = date.today()
    to_date   = today + timedelta(days=days_ahead)
    from_date = today - timedelta(days=7)   # also catch recent past actions

    url = NSE_ACTIONS_URL.format(
        from_date=from_date.strftime('%d-%m-%Y'),
        to_date=to_date.strftime('%d-%m-%Y')
    )

    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json() if resp.text else []


def fetch_earnings_calendar(session: requests.Session) -> list:
    """Fetch upcoming board meeting / results dates from NSE event calendar."""
    try:
        resp = session.get(NSE_RESULTS_URL, timeout=15)
        resp.raise_for_status()
        return resp.json() if resp.text else []
    except Exception as e:
        print(f"  ⚠ Earnings calendar fetch failed: {e}")
        return []


def store_corporate_actions(actions: list, stock_map: dict) -> int:
    """Upsert corporate actions into DB. Returns count stored."""
    conn   = get_conn()
    cursor = conn.cursor()
    count  = 0

    for item in actions:
        symbol = item.get('symbol', '').upper()
        if symbol not in stock_map:
            continue

        stock_id = stock_map[symbol]

        # Parse dates — NSE returns 'DD-Mon-YYYY' or 'YYYY-MM-DD'
        ex_date = _parse_date(item.get('exDate') or item.get('ex_date'))
        if not ex_date:
            continue

        rec_date = _parse_date(item.get('recordDate') or item.get('record_date'))
        subject  = item.get('subject', '') or item.get('purpose', '') or ''
        action_type = classify_action(subject)

        try:
            cursor.execute("""
                INSERT INTO corporate_actions
                    (stock_id, ex_date, record_date, action_type, details, ratio, amount)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (stock_id, ex_date, action_type) DO UPDATE SET
                    record_date = EXCLUDED.record_date,
                    details     = EXCLUDED.details,
                    ratio       = EXCLUDED.ratio,
                    amount      = EXCLUDED.amount
            """, (
                stock_id, ex_date, rec_date,
                action_type, subject[:500],
                parse_ratio(subject),
                parse_amount(subject),
            ))
            count += 1
        except Exception as e:
            print(f"  ⚠ {symbol} action insert error: {e}")

    conn.commit()
    cursor.close()
    conn.close()
    return count


def store_earnings_calendar(events: list, stock_map: dict) -> int:
    """Upsert upcoming earnings dates into earnings_calendar table."""
    conn   = get_conn()
    cursor = conn.cursor()
    count  = 0

    for item in events:
        symbol = (item.get('symbol') or item.get('nse_code') or '').upper()
        if symbol not in stock_map:
            continue

        results_date = _parse_date(item.get('date') or item.get('bm_date'))
        if not results_date:
            continue

        purpose = (item.get('purpose') or item.get('description') or '').lower()
        # Only care about results / quarterly / financial events
        if not any(kw in purpose for kw in ('result', 'financial', 'quarterly', 'annual', 'q1', 'q2', 'q3', 'q4')):
            continue

        stock_id = stock_map[symbol]

        try:
            cursor.execute("""
                INSERT INTO earnings_calendar
                    (stock_id, results_date, quarter, source)
                VALUES (%s, %s, %s, 'nse')
                ON CONFLICT (stock_id, results_date, quarter) DO NOTHING
            """, (stock_id, results_date, _guess_quarter(results_date)))
            count += 1
        except Exception as e:
            print(f"  ⚠ {symbol} earnings insert error: {e}")

    conn.commit()
    cursor.close()
    conn.close()
    return count


def _parse_date(raw) -> date | None:
    if not raw:
        return None
    if isinstance(raw, date):
        return raw
    for fmt in ('%d-%b-%Y', '%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(str(raw).strip(), fmt).date()
        except ValueError:
            continue
    return None


def _guess_quarter(d: date) -> str:
    """Rough guess of Indian fiscal quarter from date."""
    m = d.month
    fy = d.year if m >= 4 else d.year - 1
    quarter = {4: 'Q1', 5: 'Q1', 6: 'Q1',
               7: 'Q2', 8: 'Q2', 9: 'Q2',
               10:'Q3',11:'Q3',12:'Q3',
               1: 'Q4', 2: 'Q4', 3: 'Q4'}[m]
    return f"{quarter}FY{str(fy + 1)[-2:]}"


def collect_nse_actions(watchlist_name='Default'):
    stock_map = get_stock_id_map(watchlist_name)

    print(f"\n{'='*60}")
    print("NSE CORPORATE ACTIONS COLLECTOR")
    print(f"{'='*60}")

    with refresh_log('nse_actions') as log:
        session = get_nse_session()

        # Corporate actions
        print("\nFetching corporate actions (next 90 days)...")
        try:
            actions = fetch_corporate_actions(session)
            n = store_corporate_actions(actions, stock_map)
            print(f"  ✓ {n} actions stored for watchlist stocks")
        except Exception as e:
            print(f"  ✗ Corporate actions failed: {e}")
            n = 0

        # Earnings calendar
        print("\nFetching earnings calendar...")
        try:
            events = fetch_earnings_calendar(session)
            m = store_earnings_calendar(events, stock_map)
            print(f"  ✓ {m} earnings dates stored")
        except Exception as e:
            print(f"  ✗ Earnings calendar failed: {e}")
            m = 0

        log['rows'] = n + m

    # Print upcoming events for watchlist
    _print_upcoming_actions(stock_map)

    print(f"\n{'='*60}")
    print("✓ NSE actions collection complete")
    print(f"{'='*60}\n")


def _print_upcoming_actions(stock_map):
    """Print a summary of upcoming actions for the next 30 days."""
    stock_ids = list(stock_map.values())
    if not stock_ids:
        return

    conn   = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT s.tradingsymbol, ca.action_type, ca.ex_date, ca.details
        FROM corporate_actions ca
        JOIN stocks s ON ca.stock_id = s.id
        WHERE ca.stock_id = ANY(%s)
          AND ca.ex_date BETWEEN %s AND %s
        ORDER BY ca.ex_date
    """, (stock_ids, date.today(), date.today() + timedelta(days=30)))

    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if rows:
        print("\n📅 Upcoming actions (next 30 days):")
        print(f"  {'Symbol':<14} {'Type':<12} {'Ex-Date':<14} Details")
        print(f"  {'-'*60}")
        for sym, atype, ex_dt, details in rows:
            print(f"  {sym:<14} {atype:<12} {str(ex_dt):<14} {(details or '')[:40]}")


if __name__ == "__main__":
    collect_nse_actions()
