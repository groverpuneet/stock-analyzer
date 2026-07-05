"""
data_collectors/full_history_backfill.py

ONE-TIME full historical backfill for every NSE watchlist stock:
  - Pull up to ~2 years of daily OHLCV from yfinance ("{SYMBOL}.NS"), using raw
    (non-adjusted) Close to match existing daily_prices. Recent listings simply
    return fewer candles.
  - Polite delay between calls.
  - INSERT ... ON CONFLICT DO NOTHING — safe to re-run, never overwrites.
  - After the backfill, recompute technical indicators for all watchlist stocks.

The daily 16:00 job keeps appending new candles afterward — no change needed there.
MF instruments (NAV, not OHLCV) are skipped.
"""
import os
import sys
import time
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import psycopg2
import yfinance as yf

log = logging.getLogger(__name__)

DB_URL = os.environ.get("DATABASE_URL", "postgresql://puneetgrover@localhost/stock_analyzer")
LOOKBACK_PERIOD = "2y"       # ~2 years of daily history
DELAY = 1.0                  # polite spacing between calls

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


def _yf_rows(symbol, period):
    """Fetch daily OHLCV from yfinance; return list of (date, o, h, l, c, vol)."""
    df = yf.Ticker(f"{symbol}.NS").history(period=period, auto_adjust=False)
    rows = []
    for idx, r in df.iterrows():
        vol = r.get("Volume")
        rows.append((
            idx.date(),
            float(r["Open"]),
            float(r["High"]),
            float(r["Low"]),
            float(r["Close"]),
            int(vol) if vol == vol and vol is not None else None,  # NaN check
        ))
    return rows


def full_backfill(watchlist="Default") -> dict:
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(_STOCKS_SQL, (watchlist,))
    stocks = cur.fetchall()
    log.info(f"Full backfill: {len(stocks)} NSE watchlist stocks, up to {LOOKBACK_PERIOD} each…")

    filled, inserted, errors = 0, 0, []

    for stock_id, token, symbol in stocks:
        try:
            rows = _yf_rows(symbol, LOOKBACK_PERIOD)
            n_new = 0
            for d, o, h, l, c, v in rows:
                cur.execute(_INSERT, (stock_id, d, o, h, l, c, v))
                n_new += cur.rowcount  # 1 if inserted, 0 if conflict-skipped
            conn.commit()
            inserted += n_new
            if rows:
                filled += 1
            log.info(f"  {symbol}: {len(rows)} candles fetched, {n_new} new rows")
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
