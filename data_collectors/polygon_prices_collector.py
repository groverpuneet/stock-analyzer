"""
data_collectors/polygon_prices_collector.py

Collects US daily OHLCV bars from Polygon.io for the seeded US stock universe
and stores them in daily_prices (the same multi-market table NSE prices use).

Source: Polygon.io Aggregates (Bars) API
  GET /v2/aggs/ticker/{ticker}/range/1/day/{from}/{to}
Free tier limits: 5 API calls/minute, end-of-day data, ~2 years of history.
Key: POLYGON_API_KEY in .env (loaded via python-dotenv, same as the Kite collectors).

Rate limiting: the free tier allows 5 calls/min, so we sleep ~13s between calls
(<5/min with margin) and back off on HTTP 429.

Each bar upserts on the existing daily_prices unique key (stock_id, date).

Schedule: daily via the us_raw_prices Dagster asset (16:30 EST after the US close).
"""
import os
import sys
import time
import logging
from datetime import date, datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import get_conn, refresh_log

load_dotenv()
log = logging.getLogger(__name__)

AGGS_URL = "https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{frm}/{to}"
_CALL_INTERVAL_S = 13.0   # free tier = 5 calls/min; 13s keeps us safely under
_MAX_RETRIES = 4


def _us_stocks() -> list[tuple]:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT id, tradingsymbol FROM stocks WHERE market IN ('NYSE','NASDAQ') ORDER BY tradingsymbol")
    rows = cur.fetchall(); cur.close(); conn.close()
    return rows


def _fetch_bars(session, ticker: str, frm: str, to: str, api_key: str) -> list[dict]:
    """Fetch daily bars for one ticker, honoring 429 backoff. Returns Polygon `results`."""
    url = AGGS_URL.format(ticker=ticker, frm=frm, to=to)
    params = {"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": api_key}
    for attempt in range(_MAX_RETRIES):
        resp = session.get(url, params=params, timeout=30)
        if resp.status_code == 429:
            wait = _CALL_INTERVAL_S * (attempt + 2)
            log.warning(f"  {ticker}: 429 rate-limited — waiting {wait:.0f}s (attempt {attempt+1})")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        data = resp.json()
        return data.get("results") or []
    raise RuntimeError(f"{ticker}: still rate-limited after {_MAX_RETRIES} retries")


def _store(stock_id: int, bars: list[dict]) -> int:
    if not bars:
        return 0
    conn = get_conn(); cur = conn.cursor()
    n = 0
    for b in bars:
        # Polygon `t` is epoch ms at the start of the trading day (ET midnight) -> calendar date.
        d = datetime.fromtimestamp(b["t"] / 1000, tz=timezone.utc).date()
        cur.execute(
            """
            INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (stock_id, date) DO UPDATE SET
                open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
                close = EXCLUDED.close, volume = EXCLUDED.volume
            """,
            (stock_id, d, round(b["o"], 2), round(b["h"], 2), round(b["l"], 2),
             round(b["c"], 2), int(b["v"])),
        )
        n += 1
    conn.commit(); cur.close(); conn.close()
    return n


def collect_us_prices(years: float = 2.0, lookback_days: int | None = None) -> dict:
    """Fetch US daily OHLCV from Polygon for the US universe into daily_prices.

    Pass `lookback_days` for incremental daily runs (e.g. 7); omit it for the full
    `years`-history backfill. Either way bars upsert on (stock_id, date).
    """
    api_key = os.getenv("POLYGON_API_KEY")
    if not api_key:
        raise RuntimeError("POLYGON_API_KEY not set in environment (.env)")

    to = date.today()
    frm = to - timedelta(days=lookback_days if lookback_days else int(365 * years))
    log.info(f"=== Polygon US prices {frm}..{to} (free tier, ~13s/call) ===")

    session = requests.Session()
    stocks = _us_stocks()
    with refresh_log("us_prices") as meta:
        total_bars = 0
        stocks_done = 0
        for i, (stock_id, symbol) in enumerate(stocks):
            try:
                bars = _fetch_bars(session, symbol, frm.isoformat(), to.isoformat(), api_key)
                stored = _store(stock_id, bars)
                total_bars += stored
                if stored:
                    stocks_done += 1
                log.info(f"  {symbol}: {stored} bars ({i+1}/{len(stocks)})")
            except Exception as e:
                log.warning(f"  {symbol}: failed: {e}")
            # Rate-limit between calls (skip the wait after the final ticker).
            if i < len(stocks) - 1:
                time.sleep(_CALL_INTERVAL_S)
        meta["rows"] = total_bars

    log.info(f"us_prices: {total_bars} bars across {stocks_done}/{len(stocks)} stocks")
    return {"rows_upserted": total_bars, "stocks_with_data": stocks_done}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = collect_us_prices()
    print(f"Done: {result}")
