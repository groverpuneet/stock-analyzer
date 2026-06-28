"""
data_collectors/fno_collector.py

Collects F&O market-wide data from NSE:
  - India VIX (via allIndices API — no JS required)
  - Put/Call Ratio — index, stock, overall (NSE participant OI archive CSV)
  - FII/DII F&O positioning split

Source: NSE Archives (fao_participant_oi_{DDMMYYYY}.csv) + allIndices API
Schedule: Daily 4:45 PM IST (after market close, CSV published by ~4:30 PM)
Table: fno_data
"""
import os
import sys
import logging
from datetime import date, timedelta
from io import StringIO

import requests
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.db import get_conn, refresh_log

log = logging.getLogger(__name__)

NSE_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.nseindia.com/',
}

ARCHIVE_URL   = 'https://archives.nseindia.com/content/nsccl/fao_participant_oi_{date}.csv'
ALL_INDICES_URL = 'https://www.nseindia.com/api/allIndices'


def _get_india_vix(session: requests.Session):
    try:
        resp = session.get(ALL_INDICES_URL, headers=NSE_HEADERS, timeout=10)
        if resp.status_code == 200:
            for item in resp.json().get('data', []):
                if item.get('index') == 'INDIA VIX':
                    return float(item['last'])
    except Exception as e:
        log.warning(f"India VIX fetch failed: {e}")
    return None


def _get_participant_oi(session: requests.Session, for_date: date):
    url = ARCHIVE_URL.format(date=for_date.strftime('%d%m%Y'))
    try:
        resp = session.get(url, headers={'User-Agent': NSE_HEADERS['User-Agent']}, timeout=15)
        if resp.status_code != 200:
            return None
        df = pd.read_csv(StringIO(resp.text), skiprows=1)
        df.columns = [c.strip() for c in df.columns]
        df['Client Type'] = df['Client Type'].str.strip()
        return df
    except Exception as e:
        log.warning(f"Participant OI fetch failed for {for_date}: {e}")
        return None


def _last_trading_day() -> date:
    d = date.today()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def collect_fno_data(target_date: date = None) -> dict:
    """
    Collect F&O data for target_date (defaults to last trading day).
    Returns {'rows_inserted': int, 'date': str}.
    """
    if target_date is None:
        target_date = _last_trading_day()

    log.info(f"Collecting F&O data for {target_date}")
    session = requests.Session()

    india_vix = _get_india_vix(session)
    log.info(f"India VIX: {india_vix}")

    # Try target_date then fall back up to 3 prior trading days
    df = None
    data_date = target_date
    for delta in range(4):
        candidate = target_date - timedelta(days=delta)
        if candidate.weekday() >= 5:
            continue
        df = _get_participant_oi(session, candidate)
        if df is not None:
            data_date = candidate
            log.info(f"Participant OI loaded for {data_date}")
            break

    if df is None and india_vix is None:
        raise RuntimeError("Both India VIX and participant OI unavailable — NSE unreachable")

    # --- Parse ---
    row = {
        'date': data_date,
        'india_vix': india_vix,
        'index_call_oi': None, 'index_put_oi': None, 'index_pcr': None,
        'stock_call_oi': None, 'stock_put_oi': None, 'stock_pcr': None,
        'total_call_oi': None, 'total_put_oi': None, 'total_pcr': None,
        'fii_index_call_oi': None, 'fii_index_put_oi': None, 'fii_index_pcr': None,
        'fii_fut_index_long': None, 'fii_fut_index_short': None,
        'dii_index_call_oi': None, 'dii_index_put_oi': None, 'dii_index_pcr': None,
    }

    if df is not None:
        total = df[df['Client Type'] == 'TOTAL'].iloc[0]
        fii   = df[df['Client Type'] == 'FII'].iloc[0]
        dii   = df[df['Client Type'] == 'DII'].iloc[0]

        index_call = int(total['Option Index Call Long'])
        index_put  = int(total['Option Index Put Long'])
        stock_call = int(total['Option Stock Call Long'])
        stock_put  = int(total['Option Stock Put Long'])
        total_call = index_call + stock_call
        total_put  = index_put  + stock_put

        fii_index_call = int(fii['Option Index Call Long'])
        fii_index_put  = int(fii['Option Index Put Long'])

        dii_index_call = int(dii['Option Index Call Long'])
        dii_index_put  = int(dii['Option Index Put Long'])

        row.update({
            'index_call_oi':       index_call,
            'index_put_oi':        index_put,
            'index_pcr':           round(index_put / index_call, 3) if index_call else None,
            'stock_call_oi':       stock_call,
            'stock_put_oi':        stock_put,
            'stock_pcr':           round(stock_put / stock_call, 3) if stock_call else None,
            'total_call_oi':       total_call,
            'total_put_oi':        total_put,
            'total_pcr':           round(total_put / total_call, 3) if total_call else None,
            'fii_index_call_oi':   fii_index_call,
            'fii_index_put_oi':    fii_index_put,
            'fii_index_pcr':       round(fii_index_put / fii_index_call, 3) if fii_index_call else None,
            'fii_fut_index_long':  int(fii['Future Index Long']),
            'fii_fut_index_short': int(fii['Future Index Short']),
            'dii_index_call_oi':   dii_index_call,
            'dii_index_put_oi':    dii_index_put,
            'dii_index_pcr':       round(dii_index_put / dii_index_call, 3) if dii_index_call else None,
        })

    # --- Upsert ---
    with refresh_log('fno_data') as meta:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO fno_data (
                date, india_vix,
                index_call_oi, index_put_oi, index_pcr,
                stock_call_oi, stock_put_oi, stock_pcr,
                total_call_oi, total_put_oi, total_pcr,
                fii_index_call_oi, fii_index_put_oi, fii_index_pcr,
                fii_fut_index_long, fii_fut_index_short,
                dii_index_call_oi, dii_index_put_oi, dii_index_pcr
            ) VALUES (
                %(date)s, %(india_vix)s,
                %(index_call_oi)s, %(index_put_oi)s, %(index_pcr)s,
                %(stock_call_oi)s, %(stock_put_oi)s, %(stock_pcr)s,
                %(total_call_oi)s, %(total_put_oi)s, %(total_pcr)s,
                %(fii_index_call_oi)s, %(fii_index_put_oi)s, %(fii_index_pcr)s,
                %(fii_fut_index_long)s, %(fii_fut_index_short)s,
                %(dii_index_call_oi)s, %(dii_index_put_oi)s, %(dii_index_pcr)s
            )
            ON CONFLICT (date) DO UPDATE SET
                india_vix           = EXCLUDED.india_vix,
                index_call_oi       = EXCLUDED.index_call_oi,
                index_put_oi        = EXCLUDED.index_put_oi,
                index_pcr           = EXCLUDED.index_pcr,
                stock_call_oi       = EXCLUDED.stock_call_oi,
                stock_put_oi        = EXCLUDED.stock_put_oi,
                stock_pcr           = EXCLUDED.stock_pcr,
                total_call_oi       = EXCLUDED.total_call_oi,
                total_put_oi        = EXCLUDED.total_put_oi,
                total_pcr           = EXCLUDED.total_pcr,
                fii_index_call_oi   = EXCLUDED.fii_index_call_oi,
                fii_index_put_oi    = EXCLUDED.fii_index_put_oi,
                fii_index_pcr       = EXCLUDED.fii_index_pcr,
                fii_fut_index_long  = EXCLUDED.fii_fut_index_long,
                fii_fut_index_short = EXCLUDED.fii_fut_index_short,
                dii_index_call_oi   = EXCLUDED.dii_index_call_oi,
                dii_index_put_oi    = EXCLUDED.dii_index_put_oi,
                dii_index_pcr       = EXCLUDED.dii_index_pcr
        """, row)
        conn.commit()
        cur.close()
        conn.close()
        meta['rows'] = 1

    log.info(
        f"F&O inserted: date={data_date} vix={india_vix} "
        f"index_pcr={row['index_pcr']} fii_index_pcr={row['fii_index_pcr']}"
    )
    return {'rows_inserted': 1, 'date': str(data_date)}


if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.INFO)
    result = collect_fno_data()
    print(f"Done: {result}")
