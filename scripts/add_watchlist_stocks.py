"""
scripts/add_watchlist_stocks.py
One-off: add a batch of NSE symbols to the Default watchlist.

Looks up each symbol in the live Kite NSE instruments list, upserts the
instrument into the stocks table (ON CONFLICT no-op/update), then inserts a
Default watchlist row for it. Read-only against Kite (instruments only);
never touches portfolio/holdings/orders.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import get_conn

MARKET = 'NSE'
EXCHANGE = 'NSE'
WATCHLIST = 'Default'

SYMBOLS = [
    "AAVAS", "ALKYLAMINE", "AMRUTANJAN", "APOLLOHOSP", "ASIANPAINT", "ASTRAL",
    "AXISBANK", "BAJAJFINSV", "BAJFINANCE", "BANDHANBNK", "BANKBARODA",
    "BERGEPAINT", "CANBK", "CIPLA", "CRISIL", "CUB", "DABUR", "DATAPATTNS",
    "DEEPAKNTR", "DELHIVERY", "DELTACORP", "DIVISLAB", "DMART", "ETERNAL",
    "FEDERALBNK", "FIVESTAR", "FLUOROCHEM", "FORTIS", "GALAXYSURF", "GLAND",
    "GMMPFAUDLR", "GRAVITA", "HATHWAY", "HDFCAMC", "HDFCBANK", "HDFCLIFE",
    "HINDUNILVR", "HOMEFIRST", "ICICIBANK", "ICICIGI", "ICICIPRULI",
    "IDFCFIRSTB", "IEX", "INDHOTEL", "INDIGOPNTS", "ITBEES", "JIOFIN",
    "KALYANKJIL", "KOTAKBANK", "KWIL", "LALPATHLAB", "LTTS", "MASFIN",
    "MAXHEALTH", "MEDANTA", "NAM-INDIA", "NESTLEIND", "NH", "NIFTYBEES",
    "NMDC", "NSLNISP", "NTPC", "NYKAA", "PHARMABEES", "POWERGRID", "RALLIS",
    "SAMMAANCAP", "SBICARD", "SBILIFE", "SBIN", "SHILCTECH", "SUPRAJIT",
    "SWIGGY", "SWSOLAR", "TAJGVK", "TARSONS", "TATACHEM", "TATAPOWER",
    "TATASTEEL", "TITAN", "TORNTPOWER", "TRENT", "UJJIVANSFB", "UNITDSPR",
    "VGUARD", "VIJAYA", "VMART", "VOLTAS",
]


def _get_kite_client():
    from kiteconnect import KiteConnect
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, '.kite_access_token')) as f:
        access_token = f.read().strip()
    kite = KiteConnect(api_key=os.getenv('KITE_API_KEY'))
    kite.set_access_token(access_token)
    return kite


def main():
    kite = _get_kite_client()
    print("Fetching NSE instrument list from Kite...")
    instruments = kite.instruments('NSE')
    by_symbol = {i['tradingsymbol']: i for i in instruments}
    print(f"Fetched {len(instruments)} NSE instruments")

    conn = get_conn()
    cur = conn.cursor()

    not_found = []
    inserted_stock = 0
    added_watch = 0
    already_watch = 0

    for sym in SYMBOLS:
        inst = by_symbol.get(sym)
        if not inst:
            not_found.append(sym)
            print(f"  NOT FOUND on NSE: {sym}")
            continue

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
            RETURNING id, (xmax = 0) AS is_insert
        """, (
            inst['instrument_token'],
            inst.get('exchange_token', ''),
            inst['tradingsymbol'],
            inst.get('name', ''),
            inst['exchange'],
            inst.get('segment', 'NSE'),
            inst.get('instrument_type', 'EQ'),
            inst.get('tick_size', 0.05),
            inst.get('lot_size', 1),
            MARKET,
        ))
        stock_id, is_insert = cur.fetchone()
        if is_insert:
            inserted_stock += 1

        cur.execute("""
            INSERT INTO watchlist (stock_id, name)
            VALUES (%s, %s)
            ON CONFLICT (stock_id, name) DO NOTHING
            RETURNING id
        """, (stock_id, WATCHLIST))
        if cur.fetchone():
            added_watch += 1
        else:
            already_watch += 1

    conn.commit()

    cur.execute("SELECT COUNT(*) FROM watchlist")
    total_watch = cur.fetchone()[0]
    cur.close()
    conn.close()

    print()
    print("=== Summary ===")
    print(f"Symbols requested:        {len(SYMBOLS)}")
    print(f"Stocks newly inserted:    {inserted_stock}")
    print(f"Watchlist rows added:     {added_watch}")
    print(f"Already on watchlist:     {already_watch}")
    print(f"Not found on NSE:         {len(not_found)} {not_found}")
    print(f"SELECT COUNT(*) FROM watchlist => {total_watch}")


if __name__ == '__main__':
    main()
