"""
data_collectors/adjustment_factors_collector.py

Backtest Phase 0a. Populates `adjustment_factors` with historical split/bonus events
so a point-in-time provider can build corp-action-adjusted price series:
    adj_close(t) = raw_close(t) * PROD(price_factor for events with ex_date > t)

Source: yfinance `.splits` (SYMBOL.NS) — the historical split/bonus archive. yfinance
folds bonus issues into the split ratio, so one pull covers both. (`corporate_actions`
is only a forward ±90-day announcement window, so it cannot back-adjust history.)

    price_factor = 1 / split_ratio   (a 2:1 split -> ratio 2.0 -> 0.5 for pre-split prices)

Scope: the watchlist universe (116 stocks by default), like the other NSE collectors.
Per-ticker failures (delisted/renamed on Yahoo) are logged as gaps, not fatal.

Refresh tag: adjustment_factors. Schedule: weekly via the nse_adjustment_factors asset.
"""
import os
import sys
import time
import logging

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import get_conn, refresh_log, get_watchlist_stocks

load_dotenv()
log = logging.getLogger(__name__)

_PAUSE_S = 0.4          # polite gap between yfinance calls
_MAX_RETRIES = 3


def _fetch_splits(tradingsymbol: str) -> list[tuple]:
    """Return [(ex_date, ratio_float)] of historical splits/bonus for SYMBOL.NS."""
    import yfinance as yf
    for attempt in range(_MAX_RETRIES):
        try:
            s = yf.Ticker(f"{tradingsymbol}.NS").splits
            if s is None or len(s) == 0:
                return []
            out = []
            for ts, ratio in s.items():
                r = float(ratio)
                if r > 0:
                    out.append((ts.date(), r))
            return out
        except Exception:
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_PAUSE_S * (attempt + 2))
                continue
            raise
    return []


def _store(stock_id: int, events: list[tuple]) -> int:
    """Upsert split events as price adjustment factors (price_factor = 1/ratio)."""
    if not events:
        return 0
    conn = get_conn(); cur = conn.cursor()
    n = 0
    for ex_date, ratio in events:
        cur.execute(
            """
            INSERT INTO adjustment_factors
                (stock_id, ex_date, event_type, ratio, price_factor, source)
            VALUES (%s, %s, 'split', %s, %s, 'yfinance')
            ON CONFLICT (stock_id, ex_date, event_type, source) DO UPDATE SET
                ratio = EXCLUDED.ratio, price_factor = EXCLUDED.price_factor
            """,
            (stock_id, ex_date, f"{ratio:g}", 1.0 / ratio),
        )
        n += 1
    conn.commit(); cur.close(); conn.close()
    return n


def collect_adjustment_factors(watchlist_name: str = "Default", pause: float = _PAUSE_S) -> dict:
    """Fetch historical split/bonus events for the watchlist into adjustment_factors."""
    stocks = get_watchlist_stocks(watchlist_name)
    log.info(f"=== adjustment factors: {len(stocks)} stocks (yfinance .splits) ===")

    with refresh_log("adjustment_factors") as meta:
        total = 0
        with_events = 0
        failed = 0
        gaps: list[str] = []
        for i, (stock_id, _tok, symbol, _name) in enumerate(stocks):
            try:
                events = _fetch_splits(symbol)
                stored = _store(stock_id, events)
                total += stored
                if stored:
                    with_events += 1
                log.info(f"  {symbol}: {stored} split events ({i+1}/{len(stocks)})")
            except Exception as e:
                failed += 1
                gaps.append(symbol)
                log.warning(f"  {symbol}: failed: {e}")
            if i < len(stocks) - 1:
                time.sleep(pause)
        meta["rows"] = total
        if gaps:
            meta["gaps"] = gaps   # recorded but not marked 'partial' (rows != stock count)

    log.info(f"adjustment_factors: {total} events across {with_events} stocks, {failed} failed")
    return {"events": total, "stocks_with_events": with_events, "stocks_failed": failed}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = collect_adjustment_factors()
    print(f"Done: {result}")
