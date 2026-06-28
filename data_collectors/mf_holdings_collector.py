"""
data_collectors/mf_holdings_collector.py
Monthly refresh — nse_monthly group

Aggregates MF (DII) ownership per stock from shareholding_pattern.
Since detailed MF portfolio data requires AMFI login, we use the quarterly
DII% from Screener.in as a proxy for MF ownership.

DII (Domestic Institutional Investors) includes:
- Mutual Funds (largest component)
- Insurance companies (LIC, private)
- Banks
- Pension/Provident funds

For detailed MF holdings (which specific MFs hold which stocks), AMFI requires
authentication. This collector provides aggregate DII trends as a proxy.

Usage:
    python data_collectors/mf_holdings_collector.py
    python data_collectors/mf_holdings_collector.py --months 6
"""
import os
import sys
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import get_conn, refresh_log, get_watchlist_stocks
from utils.logger import get_logger

log = get_logger(__name__)


def get_dii_holdings_from_shareholding() -> list:
    """
    Extract DII holdings from shareholding_pattern table.
    Returns list of dicts with stock_id, quarter_end, dii_pct.
    """
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            sp.stock_id,
            s.tradingsymbol,
            sp.quarter_end,
            sp.dii_pct,
            sp.fii_pct,
            sp.promoter_pct,
            sp.public_pct
        FROM shareholding_pattern sp
        JOIN stocks s ON s.id = sp.stock_id
        WHERE sp.dii_pct IS NOT NULL
        ORDER BY sp.stock_id, sp.quarter_end DESC
    """)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    return [{
        'stock_id': r[0],
        'symbol': r[1],
        'quarter_end': r[2],
        'dii_pct': float(r[3]) if r[3] else None,
        'fii_pct': float(r[4]) if r[4] else None,
        'promoter_pct': float(r[5]) if r[5] else None,
        'public_pct': float(r[6]) if r[6] else None,
    } for r in rows]


def compute_qoq_changes(holdings: list) -> list:
    """
    Compute quarter-over-quarter changes in DII holdings.
    Returns list with mom_change_pct added (using quarterly data as proxy).
    """
    from collections import defaultdict

    # Group by stock_id
    by_stock = defaultdict(list)
    for h in holdings:
        by_stock[h['stock_id']].append(h)

    results = []
    for stock_id, stock_holdings in by_stock.items():
        # Sort by quarter_end descending
        stock_holdings.sort(key=lambda x: x['quarter_end'], reverse=True)

        for i, h in enumerate(stock_holdings):
            h['prev_dii_pct'] = None
            h['qoq_change_pct'] = None

            if i + 1 < len(stock_holdings):
                prev = stock_holdings[i + 1]
                h['prev_dii_pct'] = prev['dii_pct']
                if prev['dii_pct'] and h['dii_pct']:
                    h['qoq_change_pct'] = round(h['dii_pct'] - prev['dii_pct'], 2)

            results.append(h)

    return results


def store_mf_holdings(holdings: list) -> int:
    """
    Store MF holdings (DII proxy) in mf_stock_holdings table.
    Uses quarter_end date as the 'month' field.
    """
    conn = get_conn()
    cursor = conn.cursor()
    count = 0

    for h in holdings:
        try:
            # Convert quarter_end to first of month for consistency
            month_date = h['quarter_end'].replace(day=1)

            cursor.execute("""
                INSERT INTO mf_stock_holdings
                    (stock_id, month, total_mf_schemes, total_units, total_market_value_cr,
                     ownership_pct, mom_change_pct, top_holders, source)
                VALUES (%s, %s, NULL, NULL, NULL, %s, %s, NULL, 'shareholding_dii_proxy')
                ON CONFLICT (stock_id, month) DO UPDATE SET
                    ownership_pct = EXCLUDED.ownership_pct,
                    mom_change_pct = EXCLUDED.mom_change_pct
            """, (
                h['stock_id'], month_date,
                h['dii_pct'], h['qoq_change_pct']
            ))
            count += 1
        except Exception as e:
            log.error(f"Store MF holding failed for {h.get('symbol')}: {e}")

    conn.commit()
    cursor.close()
    conn.close()
    return count


def collect_mf_holdings(months: int = 12):
    """
    Collect MF holdings using DII% from shareholding_pattern as proxy.
    """
    print(f"\n{'='*60}")
    print("MF STOCK HOLDINGS COLLECTOR (DII Proxy)")
    print(f"{'='*60}")
    print(f"Note: Using quarterly DII% as proxy for MF ownership")
    print(f"      (detailed MF portfolio data requires AMFI login)\n")

    with refresh_log('mf_stock_holdings') as rlog:
        # Get DII holdings from shareholding_pattern
        holdings = get_dii_holdings_from_shareholding()
        log.info(f"Found {len(holdings)} shareholding records with DII data")

        if not holdings:
            print("No DII data found in shareholding_pattern")
            rlog['rows'] = 0
            return

        # Filter to last N months
        cutoff = date.today() - relativedelta(months=months)
        holdings = [h for h in holdings if h['quarter_end'] >= cutoff]
        log.info(f"Filtered to {len(holdings)} records within last {months} months")

        # Compute QoQ changes
        holdings = compute_qoq_changes(holdings)

        # Store
        count = store_mf_holdings(holdings)
        rlog['rows'] = count

        # Print summary
        print(f"\nStored {count} MF holding records\n")

        # Show top movers
        movers = [h for h in holdings if h['qoq_change_pct'] is not None]
        movers.sort(key=lambda x: abs(x['qoq_change_pct'] or 0), reverse=True)

        print(f"Top DII (MF proxy) movers (QoQ change):")
        print(f"{'Symbol':<12} {'Quarter':<12} {'DII%':>8} {'Change':>8}")
        print("-" * 44)
        for h in movers[:15]:
            change = h['qoq_change_pct'] or 0
            icon = '↑' if change > 0 else ('↓' if change < 0 else '—')
            print(f"{h['symbol']:<12} {str(h['quarter_end']):<12} {h['dii_pct']:>7.1f}% {icon}{abs(change):>6.1f}%")

    print(f"\n{'='*60}")
    print(f"✓ MF holdings complete: {count} records stored")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--months', type=int, default=12, help='Months of history to process')
    args = parser.parse_args()

    collect_mf_holdings(months=args.months)
