"""
data_collectors/expand_stock_universe.py
Weekly refresh — Sunday 07:30 IST

Pulls the full NSE EQ instrument list from Kite and upserts every equity
into the stocks table. Expands the universe from the initial 10 manually-seeded
watchlist stocks to all ~1700 NSE equities, enabling the proactive news
pipeline and signal generator to cover the full market.

Only EQ instruments are imported — futures, options, ETFs, currency,
and bond segments are excluded.

Usage:
    python data_collectors/expand_stock_universe.py
    python data_collectors/expand_stock_universe.py --dry-run   # count only, no writes
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import get_conn, refresh_log
from utils.logger import get_logger

log = get_logger(__name__)

MARKET = 'NSE'


def _get_kite_client():
    from kiteconnect import KiteConnect
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, '.kite_access_token')) as f:
        access_token = f.read().strip()
    kite = KiteConnect(api_key=os.getenv('KITE_API_KEY'))
    kite.set_access_token(access_token)
    return kite


def expand_universe(dry_run: bool = False) -> dict:
    """
    Fetch all NSE EQ instruments from Kite and upsert into stocks table.
    Returns {'total': int, 'inserted': int, 'updated': int}.
    """
    log.info("=== Expanding stock universe from Kite instruments list ===")

    kite = _get_kite_client()
    log.info("Fetching NSE instrument list from Kite...")
    all_instruments = kite.instruments('NSE')

    eq_instruments = [i for i in all_instruments if i.get('instrument_type') == 'EQ']
    log.info(f"Total instruments: {len(all_instruments)}, EQ equities: {len(eq_instruments)}")

    if dry_run:
        log.info(f"[DRY RUN] Would upsert {len(eq_instruments)} stocks — no writes made")
        return {'total': len(eq_instruments), 'inserted': 0, 'updated': 0}

    conn = get_conn()
    cur  = conn.cursor()
    inserted = updated = 0

    for inst in eq_instruments:
        cur.execute("""
            INSERT INTO stocks
                (instrument_token, exchange_token, tradingsymbol, name,
                 exchange, segment, instrument_type, tick_size, lot_size, market)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (exchange, tradingsymbol) DO UPDATE SET
                instrument_token = EXCLUDED.instrument_token,
                exchange_token   = EXCLUDED.exchange_token,
                name             = EXCLUDED.name,
                tick_size        = EXCLUDED.tick_size,
                lot_size         = EXCLUDED.lot_size,
                market           = EXCLUDED.market,
                updated_at       = CURRENT_TIMESTAMP
        """, (
            inst['instrument_token'],
            inst.get('exchange_token', ''),
            inst['tradingsymbol'],
            inst.get('name', ''),
            inst['exchange'],
            inst.get('segment', 'NSE'),
            inst['instrument_type'],
            inst.get('tick_size', 0.05),
            inst.get('lot_size', 1),
            MARKET,
        ))
        if cur.rowcount == 1:
            inserted += 1
        else:
            updated += 1

    conn.commit()
    cur.close()
    conn.close()

    log.info(f"Universe expanded — inserted: {inserted}, updated: {updated}, total: {len(eq_instruments)}")
    return {'total': len(eq_instruments), 'inserted': inserted, 'updated': updated}


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
