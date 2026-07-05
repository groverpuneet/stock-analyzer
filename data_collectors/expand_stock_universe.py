"""
data_collectors/expand_stock_universe.py
Weekly refresh — Sunday 07:30 IST

Pulls the full NSE equity symbol master from the free NSE CM (cash-market)
bhavcopy (see data_collectors/nse_bhavcopy.py) and upserts every equity into
the stocks table. Expands the universe from the initial 10 manually-seeded
watchlist stocks to all ~1700 NSE equities, enabling the proactive news
pipeline and signal generator to cover the full market.

Only the equity/ETF series (EQ, BE, ...) are imported — the bhavcopy's derivative
and other segments are handled elsewhere.

Usage:
    python data_collectors/expand_stock_universe.py
    python data_collectors/expand_stock_universe.py --dry-run   # count only, no writes
"""
import os
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import get_conn, refresh_log
from utils.logger import get_logger
from data_collectors.nse_bhavcopy import latest_cm_bhavcopy, cm_rows_by_symbol

log = get_logger(__name__)

MARKET = 'NSE'
EXCHANGE = 'NSE'


def _synthetic_token(isin: str) -> int:
    """Negative, collision-free instrument_token derived from the ISIN (stays
    negative so it never collides with real positive broker tokens)."""
    return -(zlib.crc32((isin or '').encode()) & 0x7fffffff)


def expand_universe(dry_run: bool = False) -> dict:
    """
    Build the NSE equity symbol master from the CM bhavcopy and upsert into the
    stocks table. Returns {'total': int, 'inserted': int, 'updated': int}.
    """
    log.info("=== Expanding stock universe from NSE CM bhavcopy ===")

    log.info("Fetching NSE CM bhavcopy...")
    bhav_date, rows = latest_cm_bhavcopy()
    by_symbol = cm_rows_by_symbol(rows)
    log.info(f"Bhavcopy {bhav_date}: {len(rows)} rows, {len(by_symbol)} equity symbols")

    if dry_run:
        log.info(f"[DRY RUN] Would upsert {len(by_symbol)} stocks — no writes made")
        return {'total': len(by_symbol), 'inserted': 0, 'updated': 0}

    conn = get_conn()
    cur  = conn.cursor()
    inserted = updated = 0

    for sym, row in by_symbol.items():
        isin = (row.get('ISIN') or '').strip()
        name = (row.get('FinInstrmNm') or '').strip()
        # instrument_token is set only on INSERT; existing rows keep their token.
        cur.execute("""
            INSERT INTO stocks
                (instrument_token, exchange_token, tradingsymbol, name,
                 exchange, segment, instrument_type, tick_size, lot_size, market)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (exchange, tradingsymbol) DO UPDATE SET
                name             = EXCLUDED.name,
                market           = EXCLUDED.market,
                updated_at       = CURRENT_TIMESTAMP
        """, (
            _synthetic_token(isin),
            isin,
            sym,
            name,
            EXCHANGE,
            'NSE',
            'EQ',
            0.05,
            1,
            MARKET,
        ))
        if cur.rowcount == 1:
            inserted += 1
        else:
            updated += 1

    conn.commit()
    cur.close()
    conn.close()

    log.info(f"Universe expanded — inserted: {inserted}, updated: {updated}, total: {len(by_symbol)}")
    return {'total': len(by_symbol), 'inserted': inserted, 'updated': updated}


def run_expand_universe():
    """Entry point for the scheduler."""
    with refresh_log('stock_universe') as rlog:
        result = expand_universe()
        rlog['rows'] = result['total']
    return result


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    if dry_run:
        expand_universe(dry_run=True)
    else:
        run_expand_universe()
