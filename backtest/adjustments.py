"""backtest/adjustments.py — corporate-action-adjusted price series.

IMPORTANT — know your price source's adjustment state before applying factors:
  * Current `daily_prices` comes from yfinance's Yahoo "Close", which is ALREADY
    split/bonus-adjusted (Yahoo back-adjusts splits) but NOT dividend-adjusted.
  * Future Upstox historical candles are RAW (unadjusted).

Split factors must be applied ONLY to a RAW series — applying them to an already-
split-adjusted series double-adjusts and creates a fake gap. This module is
source-state aware so the same `adjustment_factors` archive is correct for both.

Back-adjustment convention (for a RAW series):
    adj_close(t) = raw_close(t) * PROD(price_factor for events with ex_date > t)
Splits/bonus only for v1; dividend (total-return) adjustment comes later.

Factors live in `adjustment_factors` (populated by adjustment_factors_collector).
"""
import bisect

from utils.db import get_conn

# Adjustment state of a price source.
SPLIT_ADJUSTED = "split_adjusted"   # yfinance Yahoo Close — current daily_prices
RAW = "raw"                         # Upstox historical candles — future


def load_factors(stock_id: int, cur) -> list[tuple]:
    """Return [(ex_date, price_factor)] for a stock, ascending by ex_date."""
    cur.execute(
        "SELECT ex_date, price_factor FROM adjustment_factors "
        "WHERE stock_id=%s ORDER BY ex_date",
        (stock_id,),
    )
    return [(d, float(f)) for d, f in cur.fetchall()]


def _suffix_products(factors: list[tuple]):
    """(factor_dates ascending, suffix_products) where sp[i] = PROD(factor[i:])."""
    ffac = [f[1] for f in factors]
    n = len(ffac)
    sp = [1.0] * (n + 1)
    for i in range(n - 1, -1, -1):
        sp[i] = sp[i + 1] * ffac[i]
    return [f[0] for f in factors], sp


def split_adjust_raw(prices: list[tuple], factors: list[tuple]) -> list[tuple]:
    """Apply split factors to a RAW [(date, close)] series -> [(date, raw, adj)].

    A split on ex_date D scales every price strictly before D (ex_date > date), so
    the series is continuous across the event.
    """
    fdates, sp = _suffix_products(factors)
    out = []
    for d, close in prices:
        cum = sp[bisect.bisect_right(fdates, d)]
        out.append((d, float(close), round(float(close) * cum, 4)))
    return out


def adjusted_close(stock_id: int, price_state: str = SPLIT_ADJUSTED, conn=None) -> list[tuple]:
    """Return [(date, close, split_adjusted_close)] for a stock, ascending by date.

    price_state declares what the stored prices already are:
      SPLIT_ADJUSTED (default; current daily_prices / Yahoo Close) -> adjusted == close
        (splits already baked in; reapplying would double-adjust).
      RAW (Upstox candles) -> apply split factors from adjustment_factors.
    """
    own = conn is None
    if own:
        conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, close FROM daily_prices WHERE stock_id=%s ORDER BY date",
        (stock_id,),
    )
    prices = cur.fetchall()
    factors = load_factors(stock_id, cur) if price_state == RAW else []
    cur.close()
    if own:
        conn.close()

    if price_state == SPLIT_ADJUSTED:
        return [(d, float(c), float(c)) for d, c in prices]
    return split_adjust_raw(prices, factors)
