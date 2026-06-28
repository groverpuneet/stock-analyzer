"""
data_collectors/pledging_alerts_collector.py
Weekly refresh — Sunday (nse_weekly group)

Computes promoter pledging alerts from fundamentals history.
Flags: rising > 2% = red flag, falling > 2% = positive, > 50% = critical

Usage:
    python data_collectors/pledging_alerts_collector.py
    python data_collectors/pledging_alerts_collector.py --backfill
"""
import os
import sys
from datetime import date, datetime
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import get_conn, refresh_log, get_watchlist_stocks
from utils.logger import get_logger

log = get_logger(__name__)


def _determine_alert(current_pct: float, previous_pct: float, change_pct: float):
    """
    Determine alert type and severity.

    Rules:
    - > 50% pledged = CRITICAL (HIGH_PLEDGE)
    - Rising > 5% = HIGH severity
    - Rising > 2% = MEDIUM severity
    - Rising > 0% = LOW severity (RISING_PLEDGE)
    - Falling > 2% = positive (FALLING_PLEDGE, LOW severity)
    """
    if current_pct is None:
        return None, None

    alert_type = None
    severity = None

    # High pledge alert
    if current_pct >= 50:
        alert_type = 'HIGH_PLEDGE'
        severity = 'CRITICAL'
    elif current_pct >= 30:
        alert_type = 'HIGH_PLEDGE'
        severity = 'HIGH'

    # Change-based alerts (can override HIGH_PLEDGE if more severe)
    if change_pct is not None:
        if change_pct > 5:
            alert_type = 'RISING_PLEDGE'
            severity = 'HIGH'
        elif change_pct > 2:
            alert_type = 'RISING_PLEDGE'
            severity = 'MEDIUM'
        elif change_pct > 0 and current_pct >= 10:
            alert_type = 'RISING_PLEDGE'
            severity = 'LOW'
        elif change_pct < -2:
            alert_type = 'FALLING_PLEDGE'
            severity = 'LOW'  # Positive signal

    return alert_type, severity


def compute_pledging_alerts_for_stock(stock_id: int, symbol: str) -> list:
    """
    Compute pledging alerts for a single stock from its fundamentals history.
    Returns list of alert dicts to store.
    """
    conn = get_conn()
    cursor = conn.cursor()

    # Get pledged_pct history ordered by date
    cursor.execute("""
        SELECT date, pledged_pct
        FROM fundamentals
        WHERE stock_id = %s AND pledged_pct IS NOT NULL
        ORDER BY date DESC
        LIMIT 10
    """, (stock_id,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if not rows:
        return []

    alerts = []
    current_date, current_pct = rows[0]

    # Get previous value (second most recent)
    previous_pct = None
    if len(rows) >= 2:
        previous_pct = float(rows[1][1]) if rows[1][1] else None

    current_pct = float(current_pct) if current_pct else None

    if current_pct is None:
        return []

    change_pct = None
    if previous_pct is not None:
        change_pct = round(current_pct - previous_pct, 2)

    alert_type, severity = _determine_alert(current_pct, previous_pct, change_pct)

    if alert_type:
        alerts.append({
            'stock_id': stock_id,
            'date': current_date,
            'current_pledge_pct': current_pct,
            'previous_pledge_pct': previous_pct,
            'change_pct': change_pct,
            'alert_type': alert_type,
            'severity': severity,
        })

    return alerts


def store_pledging_alerts(alerts: list) -> int:
    """Store pledging alerts. Returns count stored."""
    if not alerts:
        return 0

    conn = get_conn()
    cursor = conn.cursor()
    count = 0

    for alert in alerts:
        try:
            cursor.execute("""
                INSERT INTO pledging_alerts
                    (stock_id, date, current_pledge_pct, previous_pledge_pct,
                     change_pct, alert_type, severity, resolved)
                VALUES (%s, %s, %s, %s, %s, %s, %s, false)
                ON CONFLICT (stock_id, date, alert_type) DO UPDATE SET
                    current_pledge_pct = EXCLUDED.current_pledge_pct,
                    previous_pledge_pct = EXCLUDED.previous_pledge_pct,
                    change_pct = EXCLUDED.change_pct,
                    severity = EXCLUDED.severity
            """, (
                alert['stock_id'], alert['date'],
                alert['current_pledge_pct'], alert['previous_pledge_pct'],
                alert['change_pct'], alert['alert_type'], alert['severity']
            ))
            count += 1
        except Exception as e:
            log.error(f"Store alert failed: {e}")

    conn.commit()
    cursor.close()
    conn.close()
    return count


def collect_pledging_alerts(watchlist_name: str = 'Default', backfill: bool = False):
    """
    Compute and store pledging alerts for all watchlist stocks.
    """
    print(f"\n{'='*60}")
    print("PLEDGING ALERTS COLLECTOR")
    print(f"{'='*60}")

    stocks = get_watchlist_stocks(watchlist_name)
    # Filter out MF instruments
    stocks = [(sid, tk, sym, name) for sid, tk, sym, name in stocks if not sym.startswith('INF')]

    print(f"Stocks: {len(stocks)}\n")

    with refresh_log('pledging_alerts') as rlog:
        rlog['expected'] = len(stocks)
        all_alerts = []

        for stock_id, _, symbol, name in stocks:
            alerts = compute_pledging_alerts_for_stock(stock_id, symbol)
            if alerts:
                all_alerts.extend(alerts)
                for a in alerts:
                    severity_icon = {'CRITICAL': '🔴', 'HIGH': '🟠', 'MEDIUM': '🟡', 'LOW': '🟢'}.get(a['severity'], '⚪')
                    print(f"  {severity_icon} {symbol}: {a['alert_type']} — {a['current_pledge_pct']:.1f}% (Δ {a['change_pct']:+.1f}% vs prev)")

        count = store_pledging_alerts(all_alerts)
        rlog['rows'] = count

    # Print summary by severity
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT severity, COUNT(*)
        FROM pledging_alerts
        WHERE date >= CURRENT_DATE - 30
        GROUP BY severity
        ORDER BY CASE severity
            WHEN 'CRITICAL' THEN 1
            WHEN 'HIGH' THEN 2
            WHEN 'MEDIUM' THEN 3
            WHEN 'LOW' THEN 4
        END
    """)
    severity_counts = cursor.fetchall()
    cursor.close()
    conn.close()

    if severity_counts:
        print(f"\n  Alert summary (last 30 days):")
        for sev, cnt in severity_counts:
            icon = {'CRITICAL': '🔴', 'HIGH': '🟠', 'MEDIUM': '🟡', 'LOW': '🟢'}.get(sev, '⚪')
            print(f"    {icon} {sev}: {cnt}")

    print(f"\n{'='*60}")
    print(f"✓ Pledging alerts complete: {count} alerts generated")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--backfill', action='store_true', help='Backfill from historical data')
    args = parser.parse_args()

    collect_pledging_alerts(backfill=args.backfill)
