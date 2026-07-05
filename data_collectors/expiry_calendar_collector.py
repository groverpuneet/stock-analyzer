"""
data_collectors/expiry_calendar_collector.py

Collects F&O expiry dates from the NSE F&O (UDiFF) bhavcopy — a free,
non-brokerage source (see data_collectors/nse_bhavcopy.py).

Classifies each expiry date as:
  weekly    — NIFTY-only CE/PE options expiring within 60 days (every Tuesday)
  monthly   — All stocks + FUT + CE/PE, within 95 days (end of each calendar month)
  quarterly — Long-dated index options or far monthly contracts (> 95 days out)

Source: latest_fo_bhavcopy() — public NSE F&O bhavcopy ZIP, no auth.
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
    from collections import defaultdict

    from data_collectors.nse_bhavcopy import latest_fo_bhavcopy

    log.info("Fetching F&O bhavcopy from NSE...")
    bhav_date, instruments = latest_fo_bhavcopy()
    log.info(f"Fetched {len(instruments)} F&O contracts from bhavcopy dated {bhav_date}")

    today = date.today()
    expiry_stats = defaultdict(lambda: {'FUT': 0, 'CE': 0, 'PE': 0, 'symbols': set()})
    for inst in instruments:
        key = (inst.get('XpryDt') or '').strip()[:10]  # ISO YYYY-MM-DD
        if not key:
            continue
        fin_tp = (inst.get('FinInstrmTp') or '').strip()
        if fin_tp in ('STF', 'IDF'):
            inst_type = 'FUT'
        else:
            inst_type = (inst.get('OptnTp') or '').strip()  # CE / PE
        if inst_type in ('FUT', 'CE', 'PE'):
            expiry_stats[key][inst_type] += 1
        expiry_stats[key]['symbols'].add((inst.get('TckrSymb') or '').strip())

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
                VALUES (%s, %s, 'NFO', %s, %s, 'nse_bhavcopy', NOW())
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
