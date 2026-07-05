"""
scripts/add_mf_watchlist.py
One-off: add mutual funds to the Default watchlist for NAV tracking only.

Uses AMFI's public NAVAll.txt scheme list (no brokerage/auth). Matches each
requested fund name to a Direct-plan / Growth-option scheme (the standard for
NAV tracking), upserts it into the stocks table with market='MF',
instrument_type='MF', then adds a Default watchlist row. MF schemes have no
broker instrument_token, so a synthetic, collision-free negative token is
derived from the ISIN (stays negative so it never collides with real broker tokens).

  --dry-run   show the chosen match per fund, write nothing
"""
import os
import sys
import re
import zlib
from difflib import SequenceMatcher

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import get_conn
from data_collectors.amfi_nav_collector import fetch_amfi_schemes

MARKET = 'MF'
EXCHANGE = 'MF'
WATCHLIST = 'Default'

# requested fund -> required AMC keyword (disambiguates Quant vs Quantum, etc.)
TARGETS = [
    ("Quantum Small Cap Fund", "quantum"),
    ("HDFC Small Cap Fund", "hdfc"),
    ("SBI Contra Fund", "sbi"),
    ("ICICI Prudential Value Fund", "icici"),
    ("JioBlackRock Flexi Cap Fund", "jioblackrock"),
    ("Navi Nifty 50 Index Fund", "navi"),
    ("Navi Nifty Bank Index Fund", "navi"),
    ("JioBlackRock Nifty Smallcap 250 Index Fund", "jioblackrock"),
    ("Parag Parikh Flexi Cap Fund", "ppfas"),
    ("Tata Nifty MidSmall Healthcare Index Fund", "tata"),
    ("Quant Small Cap Fund", "quant"),
    ("HDFC Flexi Cap Fund", "hdfc"),
    ("ICICI Prudential Nifty Pharma Index Fund", "icici"),
    ("Parag Parikh ELSS Tax Saver Fund", "ppfas"),
    ("ICICI Prudential Nifty Smallcap 250 Index Fund", "icici"),
    ("ICICI Prudential Nifty 50 Index Fund", "icici"),
    ("Navi Nifty Midcap 150 Index Fund", "navi"),
    ("Axis Small Cap Fund", "axis"),
]

_STOP = {"fund", "plan", "direct", "regular", "growth", "the", "scheme", "option"}


def norm(s):
    s = s.lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    toks = [t for t in s.split() if t not in _STOP]
    return toks


def score(target_toks, cand_toks):
    ts, cs = set(target_toks), set(cand_toks)
    if not ts:
        return 0.0
    tj, cj = " ".join(target_toks), " ".join(cand_toks)
    overlap = len(ts & cs) / len(ts)
    seq = SequenceMatcher(None, tj, cj).ratio()
    base = 0.7 * overlap + 0.3 * seq
    # Bonus when the full target phrase appears verbatim in the candidate — cleanly
    # separates e.g. "Nifty 50 Index" from "Nifty Next 50 Index".
    if tj and tj in cj:
        base += 0.2
    return base


def scheme_isin(m):
    """Primary ISIN of an AMFI scheme (growth/payout column, fall back to reinvest)."""
    isin = (m.get('isin') or '').strip()
    if isin and isin != '-':
        return isin
    isin2 = (m.get('isin2') or '').strip()
    return isin2 if isin2 and isin2 != '-' else ''


def _is_direct_growth(name):
    n = name.lower()
    is_direct = 'direct' in n
    is_growth = 'growth' in n or not any(
        w in n for w in ('idcw', 'dividend', 'reinvest', 'payout', 'bonus'))
    return is_direct and is_growth


def _amc_matches(m, amc_kw):
    # Space-insensitive: AMFI writes "Jio BlackRock", targets use "jioblackrock".
    hay = (m.get('amc', '') + ' ' + m.get('name', '')).lower().replace(' ', '')
    return amc_kw.replace(' ', '') in hay


def best_match(target, amc_kw, mf):
    ttoks = norm(target)
    # prefer Direct + Growth schemes within the requested AMC
    amc_pool = [m for m in mf if _amc_matches(m, amc_kw) and scheme_isin(m)]
    pref = [m for m in amc_pool if _is_direct_growth(m['name'])]
    pool = pref or amc_pool
    scored = sorted(
        ((score(ttoks, norm(m['name'])), m) for m in pool),
        key=lambda x: x[0], reverse=True)
    return scored[:3]


def main(dry):
    print("Fetching MF scheme list from AMFI (NAVAll.txt)...")
    mf = fetch_amfi_schemes()
    print(f"Fetched {len(mf)} MF schemes\n")

    chosen = []
    for target, amc_kw in TARGETS:
        top = best_match(target, amc_kw, mf)
        if not top:
            print(f"!! NO MATCH: {target}")
            continue
        sc, m = top[0]
        chosen.append((target, m))
        print(f"[{sc:.2f}] {target}")
        print(f"      -> {m['name']}  | amc={m['amc']} "
              f"| isin={scheme_isin(m)} | nav={m['nav']}")
        for sc2, m2 in top[1:]:
            print(f"         alt [{sc2:.2f}] {m2['name']}")
    print(f"\nMatched {len(chosen)}/{len(TARGETS)} funds")

    if dry:
        print("\n[DRY RUN] no writes made")
        return

    conn = get_conn()
    cur = conn.cursor()
    added_watch = inserted_stock = already_watch = 0
    for target, m in chosen:
        isin = scheme_isin(m)
        token = -(zlib.crc32(isin.encode()) & 0x7fffffff)
        cur.execute("""
            INSERT INTO stocks
                (instrument_token, exchange_token, tradingsymbol, name,
                 exchange, segment, instrument_type, tick_size, lot_size, market)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (exchange, tradingsymbol) DO UPDATE SET
                instrument_token = EXCLUDED.instrument_token,
                name             = EXCLUDED.name,
                market           = EXCLUDED.market,
                instrument_type  = EXCLUDED.instrument_type,
                updated_at       = CURRENT_TIMESTAMP
            RETURNING id, (xmax = 0) AS is_insert
        """, (
            token, isin, isin, m['name'],
            EXCHANGE, 'MF', 'MF', 0.0001, 1, MARKET,
        ))
        stock_id, is_insert = cur.fetchone()
        if is_insert:
            inserted_stock += 1
        cur.execute("""
            INSERT INTO watchlist (stock_id, name, notes)
            VALUES (%s, %s, %s)
            ON CONFLICT (stock_id, name) DO NOTHING
            RETURNING id
        """, (stock_id, WATCHLIST, f"MF NAV tracking: {target}"))
        if cur.fetchone():
            added_watch += 1
        else:
            already_watch += 1

    conn.commit()
    cur.execute("SELECT COUNT(*) FROM watchlist")
    total = cur.fetchone()[0]
    cur.close()
    conn.close()
    print("\n=== Summary ===")
    print(f"Funds matched:         {len(chosen)}")
    print(f"Stocks newly inserted: {inserted_stock}")
    print(f"Watchlist rows added:  {added_watch}")
    print(f"Already on watchlist:  {already_watch}")
    print(f"COUNT(*) watchlist =>  {total}")


if __name__ == '__main__':
    main('--dry-run' in sys.argv)
