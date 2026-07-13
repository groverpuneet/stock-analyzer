"""
data_collectors/survivorship_collector.py

Backtest Phase 0b. Populates stocks.listing_date/is_active from NSE's official
current mainboard list (EQUITY_L.csv) so a point-in-time backtest can exclude
stocks that hadn't listed yet as of a given `as_of` date.

Scope, deliberately conservative (see migration 0027 docstring for the full reasoning):
`stocks` is a broad historical NSE symbol master (~10.7k rows spanning mainboard, SME,
and legacy tickers), while EQUITY_L.csv only covers the ~2.4k names CURRENTLY on the
mainboard. So this collector only ever sets is_active=TRUE + listing_date for a
POSITIVE match — it never flips is_active to FALSE, because "absent from
EQUITY_L.csv" also matches SME-listed stocks, ETFs, and non-NSE rows, none of which
are actually delisted. True delisted-name identification is deferred to a historical
index-membership backfill (tracked in TASKS.md).

Refresh tag: survivorship_master. Schedule: weekly via the nse_survivorship_master asset.
"""
import csv
import io
import logging

from data_collectors.nse_bhavcopy import _session
from utils.db import get_conn, refresh_log

log = logging.getLogger(__name__)

EQUITY_L_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"


def fetch_mainboard_listing_dates() -> dict[str, str]:
    """Return {tradingsymbol: 'YYYY-MM-DD'} for every NSE mainboard equity."""
    r = _session().get(EQUITY_L_URL, timeout=20)
    r.raise_for_status()
    rows = csv.DictReader(io.StringIO(r.text))
    out = {}
    for row in rows:
        symbol = row["SYMBOL"].strip()
        raw_date = row[" DATE OF LISTING"].strip()
        from datetime import datetime
        out[symbol] = datetime.strptime(raw_date, "%d-%b-%Y").strftime("%Y-%m-%d")
    return out


def collect_survivorship_master() -> dict:
    """Match stocks.tradingsymbol against EQUITY_L.csv; set listing_date + is_active=TRUE
    on matches only (never flips anything to FALSE — see module docstring)."""
    listing_dates = fetch_mainboard_listing_dates()
    log.info(f"=== survivorship master: {len(listing_dates)} mainboard symbols ===")

    conn = get_conn()
    cur = conn.cursor()

    with refresh_log("survivorship_master") as meta:
        cur.execute("SELECT id, tradingsymbol FROM stocks WHERE market='NSE'")
        stocks = cur.fetchall()

        matched = 0
        for stock_id, symbol in stocks:
            listing_date = listing_dates.get(symbol)
            if listing_date:
                cur.execute(
                    "UPDATE stocks SET listing_date=%s, is_active=TRUE WHERE id=%s",
                    (listing_date, stock_id),
                )
                matched += 1
        conn.commit()

        cur.execute(
            "SELECT count(*) FROM stocks s JOIN watchlist w ON w.stock_id=s.id "
            "WHERE s.market='NSE' AND s.listing_date IS NULL"
        )
        unmatched_watchlist = cur.fetchone()[0]

        meta["rows"] = matched
        if unmatched_watchlist:
            meta["gaps"] = [f"{unmatched_watchlist} watchlist NSE stocks unmatched"]

    cur.close()
    conn.close()

    log.info(
        f"survivorship_master: {matched}/{len(stocks)} NSE stocks matched to mainboard listing dates "
        f"({unmatched_watchlist} watchlist stocks unmatched — expected for ETFs/non-mainboard names)"
    )
    return {"matched": matched, "total_nse_stocks": len(stocks), "unmatched_watchlist": unmatched_watchlist}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    collect_survivorship_master()
