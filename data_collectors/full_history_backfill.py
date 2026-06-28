"""
data_collectors/full_history_backfill.py

ONE-TIME full historical backfill for every NSE watchlist stock:
  - Pull up to 2 years of daily OHLCV from Kite historical_data (Kite's day-candle
    window). Recent listings simply return fewer candles.
  - Polite 0.5s delay between calls; on 429 wait 60s and retry once.
  - INSERT ... ON CONFLICT DO NOTHING — safe to re-run, never overwrites.
  - After the backfill, recompute technical indicators for all watchlist stocks.

The daily 16:00 job keeps appending new candles afterward — no change needed there.
Read-only Kite usage (historical_data only). MF instruments (NAV, not OHLCV) skipped.
"""
import os
import sys
import time
import logging
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import psycopg2

log = logging.getLogger(__name__)

DB_URL = os.environ.get("DATABASE_URL", "postgresql://puneetgrover@localhost/stock_analyzer")
LOOKBACK_DAYS = 730          # ~2 years (Kite day-candle limit)
DELAY = 0.5                  # polite spacing between calls
TOKEN_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".kite_access_token")

_STOCKS_SQL = """
    SELECT s.id, s.instrument_token, s.tradingsymbol
    FROM watchlist w JOIN stocks s ON w.stock_id = s.id
    WHERE w.name = %s AND s.exchange = 'NSE' AND s.instrument_token IS NOT NULL
    ORDER BY s.tradingsymbol
"""

_INSERT = """
    INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (stock_id, date) DO NOTHING
"""


def _kite():
    from kiteconnect import KiteConnect
    kite = KiteConnect(api_key=os.getenv("KITE_API_KEY"))
    kite.set_access_token(open(TOKEN_PATH).read().strip())
    return kite


def _fetch_with_retry(kite, token, from_date, to_date):
    """One retry on rate-limit (429 / 'Too many requests')."""
    try:
        return kite.historical_data(token, from_date, to_date, "day")
    except Exception as e:  # noqa: BLE001
        if "Too many requests" in str(e) or "429" in str(e):
            log.warning("  rate limited — sleeping 60s then retrying once")
            time.sleep(60)
            return kite.historical_data(token, from_date, to_date, "day")
        raise


def full_backfill(watchlist="Default") -> dict:
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(_STOCKS_SQL, (watchlist,))
    stocks = cur.fetchall()
    log.info(f"Full backfill: {len(stocks)} NSE watchlist stocks, up to {LOOKBACK_DAYS}d each…")

    kite = _kite()
    to_date = datetime.now()
    from_date = to_date - timedelta(days=LOOKBACK_DAYS)
    filled, inserted, errors = 0, 0, []

    for stock_id, token, symbol in stocks:
        try:
            candles = _fetch_with_retry(kite, token, from_date, to_date)
            before = cur.rowcount  # not reliable across executes; count via len + conflict
            n_new = 0
            for c in candles:
                cur.execute(_INSERT, (stock_id, c["date"].date(), c["open"], c["high"],
                                      c["low"], c["close"], c["volume"]))
                n_new += cur.rowcount  # 1 if inserted, 0 if conflict-skipped
            conn.commit()
            inserted += n_new
            if candles:
                filled += 1
            log.info(f"  {symbol}: {len(candles)} candles fetched, {n_new} new rows")
        except Exception as e:  # noqa: BLE001
            conn.rollback()
            errors.append({"symbol": symbol, "error": str(e)[:200]})
            log.warning(f"  {symbol}: FAILED — {str(e)[:160]}")
        time.sleep(DELAY)

    cur.close()
    conn.close()
    result = {"stocks": len(stocks), "stocks_filled": filled, "rows_inserted": inserted,
              "errors": errors}
    log.info(f"Backfill done: {filled}/{len(stocks)} stocks, {inserted} new rows, {len(errors)} errors")
    return result


def run():
    res = full_backfill()
    log.info("Recomputing technical indicators for all watchlist stocks…")
    try:
        from analysis.calculate_indicators import process_all_watchlist_stocks
        process_all_watchlist_stocks(watchlist_name="Default")
        log.info("Technical indicators recomputed.")
        res["indicators_recomputed"] = True
    except Exception as e:  # noqa: BLE001
        log.error(f"Indicator recompute failed: {e}", exc_info=True)
        res["indicators_recomputed"] = False
    return res


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    r = run()
    print(f"\nDONE: {r['stocks_filled']}/{r['stocks']} stocks, {r['rows_inserted']} new rows, "
          f"{len(r['errors'])} errors, indicators={r.get('indicators_recomputed')}")
    for e in r["errors"][:15]:
        print(f"  ERR {e['symbol']}: {e['error'][:120]}")
