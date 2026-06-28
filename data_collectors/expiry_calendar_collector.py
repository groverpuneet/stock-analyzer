"""
data_collectors/expiry_calendar_collector.py

Collects F&O expiry dates from Kite Connect NFO instrument list.

Classifies each expiry date as:
  weekly    — NIFTY-only CE/PE options expiring within 60 days (every Tuesday)
  monthly   — All stocks + FUT + CE/PE, within 95 days (end of each calendar month)
  quarterly — Long-dated index options or far monthly contracts (> 95 days out)

Source: Kite Connect instruments('NFO') — no extra API call beyond what kite_collector already uses.
Schedule: Weekly Sunday 07:30 IST (nse_weekly group, via nse_expiry_calendar Dagster asset)
Table: expiry_calendar
"""
import os
import sys
import logging
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from utils.db import get_conn, refresh_log

log = logging.getLogger(__name__)


def _classify(expiry_dt: date, has_futures: bool, symbol_count: int, today: date) -> str:
    days_out = (expiry_dt - today).days
    if has_futures:
        return 'monthly' if days_out <= 95 else 'quarterly'
    return 'weekly' if (symbol_count == 1 and days_out <= 60) else 'quarterly'


def collect_expiry_calendar() -> dict:
    from kiteconnect import KiteConnect
    from collections import defaultdict

    api_key = os.getenv('KITE_API_KEY')
    token_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.kite_access_token')
    access_token = open(token_path).read().strip()

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)

    log.info("Fetching NFO instruments from Kite...")
    instruments = kite.instruments('NFO')
    log.info(f"Fetched {len(instruments)} NFO instruments")

    today = date.today()
    expiry_stats = defaultdict(lambda: {'FUT': 0, 'CE': 0, 'PE': 0, 'symbols': set()})
    for inst in instruments:
        if not inst.get('expiry'):
            continue
        exp_date = inst['expiry']  # already a date object from kiteconnect
        key = exp_date.isoformat()
        inst_type = inst.get('instrument_type', '')
        if inst_type in ('FUT', 'CE', 'PE'):
            expiry_stats[key][inst_type] += 1
        expiry_stats[key]['symbols'].add(inst.get('name', ''))

    rows = []
    for date_str, stats in sorted(expiry_stats.items()):
        exp_date = date.fromisoformat(date_str)
        has_fut = stats['FUT'] > 0
        sym_count = len(stats['symbols'])
        expiry_type = _classify(exp_date, has_fut, sym_count, today)
        rows.append({
            'expiry_date': exp_date,
            'expiry_type': expiry_type,
            'symbol_count': sym_count,
            'has_futures': has_fut,
        })

    upserted = 0
    with refresh_log('nse_expiry_calendar') as meta:
        conn = get_conn()
        cur = conn.cursor()
        for row in rows:
            cur.execute(
                """
                INSERT INTO expiry_calendar
                    (expiry_date, expiry_type, segment, symbol_count, has_futures, source, fetched_at)
                VALUES (%s, %s, 'NFO', %s, %s, 'kite_nfo', NOW())
                ON CONFLICT (expiry_date) DO UPDATE SET
                    expiry_type  = EXCLUDED.expiry_type,
                    symbol_count = EXCLUDED.symbol_count,
                    has_futures  = EXCLUDED.has_futures,
                    fetched_at   = EXCLUDED.fetched_at
                """,
                (row['expiry_date'], row['expiry_type'], row['symbol_count'], row['has_futures'])
            )
            upserted += 1
        conn.commit()
        cur.close()
        conn.close()
        meta['rows'] = upserted

    log.info(f"expiry_calendar: {upserted} rows upserted ({len([r for r in rows if r['expiry_type']=='weekly'])} weekly, "
             f"{len([r for r in rows if r['expiry_type']=='monthly'])} monthly, "
             f"{len([r for r in rows if r['expiry_type']=='quarterly'])} quarterly)")
    return {
        'rows_upserted': upserted,
        'weekly': len([r for r in rows if r['expiry_type'] == 'weekly']),
        'monthly': len([r for r in rows if r['expiry_type'] == 'monthly']),
        'quarterly': len([r for r in rows if r['expiry_type'] == 'quarterly']),
    }


if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    result = collect_expiry_calendar()
    print(f"Done: {result}")
