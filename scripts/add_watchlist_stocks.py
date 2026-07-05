"""
scripts/add_watchlist_stocks.py
One-off: add a batch of NSE symbols to the Default watchlist.

Looks up each symbol in the free NSE CM bhavcopy symbol master (see
data_collectors/nse_bhavcopy.py), upserts the instrument into the stocks table
(ON CONFLICT no-op/update), then inserts a Default watchlist row for it. New
stock rows get a synthetic negative instrument_token derived from the ISIN.
"""
import os
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import get_conn
from data_collectors.nse_bhavcopy import latest_cm_bhavcopy, cm_rows_by_symbol

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


def _synthetic_token(isin: str) -> int:
    """Negative, collision-free instrument_token derived from the ISIN."""
    return -(zlib.crc32((isin or '').encode()) & 0x7fffffff)


def main():
    print("Fetching NSE CM bhavcopy symbol master...")
    bhav_date, rows = latest_cm_bhavcopy()
    by_symbol = cm_rows_by_symbol(rows)
    print(f"Bhavcopy {bhav_date}: {len(by_symbol)} equity symbols")

    conn = get_conn()
    cur = conn.cursor()

    not_found = []
    inserted_stock = 0
    added_watch = 0
    already_watch = 0

    for sym in SYMBOLS:
        row = by_symbol.get(sym)
        if not row:
            not_found.append(sym)
            print(f"  NOT FOUND on NSE: {sym}")
            continue

        isin = (row.get('ISIN') or '').strip()
        name = (row.get('FinInstrmNm') or '').strip()
        # instrument_token set only on INSERT; existing rows keep their token.
        cur.execute("""
            INSERT INTO stocks
                (instrument_token, exchange_token, tradingsymbol, name,
                 exchange, segment, instrument_type, tick_size, lot_size, market)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (exchange, tradingsymbol) DO UPDATE SET
                name             = EXCLUDED.name,
                market           = EXCLUDED.market,
                updated_at       = CURRENT_TIMESTAMP
            RETURNING id, (xmax = 0) AS is_insert
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
