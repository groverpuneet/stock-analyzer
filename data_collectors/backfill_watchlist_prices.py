"""
data_collectors/backfill_watchlist_prices.py

One-shot / on-demand backfill: fetch the last N days of daily OHLCV for every
watchlist stock that has no recent daily_prices.

Used by:
  - manual run after new stocks are added to a watchlist
  - the Dagster watchlist_change_sensor path (nse_daily_job covers the ongoing case)

Only NSE equities/ETFs are fetched (Kite historical_data needs an NSE instrument
token). Mutual-fund instruments (exchange='MF') carry NAV, not OHLCV, so they're
skipped. Read-only Kite usage — historical_data only.
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
RATE_LIMIT_SEC = 0.35  # Kite historical API allows ~3 req/s; stay under it

_STALE_SQL = """
    SELECT s.id, s.instrument_token, s.tradingsymbol
    FROM watchlist w
    JOIN stocks s ON w.stock_id = s.id
    WHERE w.name = %s
      AND s.exchange = 'NSE'
      AND s.instrument_token IS NOT NULL
      AND NOT EXISTS (
        SELECT 1 FROM daily_prices dp
        WHERE dp.stock_id = s.id
          AND dp.date >= CURRENT_DATE - (%s || ' days')::interval
      )
    ORDER BY s.tradingsymbol
"""

_UPSERT = """
    INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (stock_id, date) DO UPDATE
    SET open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
        close = EXCLUDED.close, volume = EXCLUDED.volume
"""


def _kite():
    from kiteconnect import KiteConnect
    token_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".kite_access_token")
    kite = KiteConnect(api_key=os.getenv("KITE_API_KEY"))
    kite.set_access_token(open(token_path).read().strip())
    return kite


def backfill_stale_watchlist_prices(watchlist_name: str = "Default", days: int = 30) -> dict:
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(_STALE_SQL, (watchlist_name, days))
    stale = cur.fetchall()

    if not stale:
        log.info(f"No stale stocks in '{watchlist_name}' — every NSE stock has prices in the last {days} days.")
        cur.close(); conn.close()
        return {"stale_stocks": 0, "stocks_filled": 0, "rows_upserted": 0, "errors": []}

    log.info(f"Backfilling {len(stale)} stale NSE stocks in '{watchlist_name}' ({days}d each)…")
    kite = _kite()
    to_date = datetime.now()
    from_date = to_date - timedelta(days=days)

    filled, total_rows, errors = 0, 0, []
    for stock_id, token, symbol in stale:
        try:
            candles = kite.historical_data(token, from_date, to_date, "day")
            n = 0
            for c in candles:
                cur.execute(_UPSERT, (stock_id, c["date"].date(), c["open"], c["high"],
                                      c["low"], c["close"], c["volume"]))
                n += 1
            conn.commit()
            total_rows += n
            if n:
                filled += 1
            log.info(f"  {symbol}: {n} days")
        except Exception as e:  # noqa: BLE001
            conn.rollback()
            msg = str(e)
            errors.append({"symbol": symbol, "error": msg[:200]})
            log.warning(f"  {symbol}: FAILED — {msg[:160]}")
            # Kite throttling: back off and continue
            if "Too many requests" in msg or "rate" in msg.lower():
                log.warning("  rate limited — sleeping 60s")
                time.sleep(60)
        time.sleep(RATE_LIMIT_SEC)

    cur.close()
    conn.close()
    result = {"stale_stocks": len(stale), "stocks_filled": filled,
              "rows_upserted": total_rows, "errors": errors}
    log.info(f"Backfill done: {filled}/{len(stale)} stocks filled, {total_rows} rows, {len(errors)} errors")
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    days = next((int(a) for a in sys.argv[1:] if a.isdigit()), 30)
    res = backfill_stale_watchlist_prices(days=days)
    print(f"\nDone: {res['stocks_filled']}/{res['stale_stocks']} filled, "
          f"{res['rows_upserted']} rows, {len(res['errors'])} errors")
    if res["errors"]:
        for e in res["errors"][:10]:
            print(f"  ERR {e['symbol']}: {e['error'][:100]}")
