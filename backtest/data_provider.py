"""backtest/data_provider.py — point-in-time data panels for the backtest engine.

Wraps Postgres+pandas into the wide (date x symbol) panels vectorbt wants, applying
the survivorship/adjustment rules built in Phase 0:
  - Universe membership uses stocks.listing_date (Phase 0b) so a backtest never
    includes a stock before it actually listed.
  - Prices come straight from daily_prices, which (Yahoo Close) is ALREADY split/bonus
    adjusted — see backtest/adjustments.py. adjustment_factors is NOT applied here;
    it exists for a future RAW source (Upstox), not this one.
  - Signals come from signal_explanations, populated going forward by the live
    nse_signals asset and backfillable historically via
    signals.engine.run_signals(as_of=<past date>) (Phase 0c).
"""
from datetime import date

import pandas as pd

from utils.db import get_conn


def load_universe(watchlist: str = "Default", end: date | None = None) -> list[dict]:
    """Stocks in `watchlist` that had (or may have) listed by `end`.

    listing_date IS NULL means unreconciled against NSE's mainboard list (SME/ETF/etc,
    not evidence of not-yet-listed — see survivorship_collector.py), so it's included,
    not excluded.
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT s.id, s.tradingsymbol FROM watchlist w JOIN stocks s ON w.stock_id=s.id "
                "WHERE w.name=%s AND s.market <> 'MF' "
                "AND (s.listing_date IS NULL OR s.listing_date <= %s) "
                "ORDER BY s.tradingsymbol",
                (watchlist, end or date.today()),
            )
            return [{"id": sid, "symbol": sym} for sid, sym in cur.fetchall()]
    finally:
        conn.close()


def load_price_panel(stocks: list[dict], start: date, end: date) -> pd.DataFrame:
    """Wide close-price panel: index=date, columns=symbol. Already split-adjusted."""
    conn = get_conn()
    try:
        ids = [s["id"] for s in stocks]
        id_to_symbol = {s["id"]: s["symbol"] for s in stocks}
        with conn.cursor() as cur:
            cur.execute(
                "SELECT stock_id, date, close FROM daily_prices "
                "WHERE stock_id = ANY(%s) AND date BETWEEN %s AND %s",
                (ids, start, end),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    df = pd.DataFrame(rows, columns=["stock_id", "date", "close"])
    if df.empty:
        return pd.DataFrame(index=pd.DatetimeIndex([]), columns=[s["symbol"] for s in stocks], dtype=float)
    df["symbol"] = df["stock_id"].map(id_to_symbol)
    panel = df.pivot(index="date", columns="symbol", values="close").astype(float)
    panel.index = pd.DatetimeIndex(panel.index)
    return panel.sort_index()


def load_signal_panel(stocks: list[dict], start: date, end: date, horizon: str = "MID") -> pd.DataFrame:
    """Wide overall_score panel: index=date, columns=symbol, from signal_explanations."""
    conn = get_conn()
    try:
        ids = [s["id"] for s in stocks]
        id_to_symbol = {s["id"]: s["symbol"] for s in stocks}
        with conn.cursor() as cur:
            cur.execute(
                "SELECT stock_id, date, overall_score FROM signal_explanations "
                "WHERE stock_id = ANY(%s) AND horizon=%s AND date BETWEEN %s AND %s",
                (ids, horizon, start, end),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    if not rows:
        return pd.DataFrame(index=pd.DatetimeIndex([]), columns=[s["symbol"] for s in stocks], dtype=float)
    df = pd.DataFrame(rows, columns=["stock_id", "date", "overall_score"])
    df["symbol"] = df["stock_id"].map(id_to_symbol)
    panel = df.pivot(index="date", columns="symbol", values="overall_score").astype(float)
    panel.index = pd.DatetimeIndex(panel.index)
    return panel.sort_index()
