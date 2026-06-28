"""Signal engine — ports analysis/generate_signals.py rules to the web layer.

Signals are not stored in a table; they are derived on demand from the latest
technical_indicators + daily_prices. Same thresholds as the CLI report:
  RSI < 30 -> BUY (STRONG < 25),  RSI > 70 -> SELL (STRONG > 75)
  SMA50/200 golden/death cross, price/SMA20 cross, MACD cross, Bollinger bands,
  volume spike (> 2x trailing 4-day avg) -> WATCH.

Each stock is reduced to one overall verdict for the dashboard table, while the
individual rule hits are kept for the detail view.
"""
from db import get_cursor

_RECENT_SQL = """
    SELECT dp.date, dp.close, dp.volume,
           ti.rsi_14, ti.sma_20, ti.sma_50, ti.sma_200,
           ti.macd, ti.macd_signal, ti.macd_histogram,
           ti.bollinger_upper, ti.bollinger_lower
    FROM daily_prices dp
    LEFT JOIN technical_indicators ti
      ON dp.stock_id = ti.stock_id AND dp.date = ti.date
    WHERE dp.stock_id = %s
    ORDER BY dp.date DESC
    LIMIT 5
"""


import math


def _f(v):
    if v is None:
        return None
    f = float(v)
    return None if (math.isnan(f) or math.isinf(f)) else f


def _rule_hits(rows: list[dict]) -> list[dict]:
    """rows are most-recent-first; evaluate the same rules as the CLI report."""
    if not rows:
        return []
    cur = rows[0]
    prev = rows[1] if len(rows) > 1 else None
    hits = []

    rsi = _f(cur["rsi_14"])
    if rsi is not None:
        if rsi < 30:
            hits.append({"type": "RSI_OVERSOLD", "signal": "BUY",
                         "strength": "STRONG" if rsi < 25 else "MODERATE",
                         "message": f"RSI {rsi:.1f} — oversold"})
        elif rsi > 70:
            hits.append({"type": "RSI_OVERBOUGHT", "signal": "SELL",
                         "strength": "STRONG" if rsi > 75 else "MODERATE",
                         "message": f"RSI {rsi:.1f} — overbought"})

    if prev:
        c50, c200 = _f(cur["sma_50"]), _f(cur["sma_200"])
        p50, p200 = _f(prev["sma_50"]), _f(prev["sma_200"])
        if None not in (c50, c200, p50, p200):
            if p50 <= p200 and c50 > c200:
                hits.append({"type": "GOLDEN_CROSS", "signal": "BUY", "strength": "STRONG",
                             "message": "Golden cross — SMA50 above SMA200"})
            elif p50 >= p200 and c50 < c200:
                hits.append({"type": "DEATH_CROSS", "signal": "SELL", "strength": "STRONG",
                             "message": "Death cross — SMA50 below SMA200"})

        c20, pc = _f(cur["sma_20"]), _f(prev["close"])
        p20 = _f(prev["sma_20"])
        cc = _f(cur["close"])
        if None not in (c20, p20, pc, cc):
            if pc <= p20 and cc > c20:
                hits.append({"type": "PRICE_ABOVE_SMA20", "signal": "BUY", "strength": "MODERATE",
                             "message": "Price crossed above 20-SMA"})
            elif pc >= p20 and cc < c20:
                hits.append({"type": "PRICE_BELOW_SMA20", "signal": "SELL", "strength": "MODERATE",
                             "message": "Price crossed below 20-SMA"})

        cm, cs = _f(cur["macd"]), _f(cur["macd_signal"])
        pm, ps = _f(prev["macd"]), _f(prev["macd_signal"])
        if None not in (cm, cs, pm, ps):
            if pm <= ps and cm > cs:
                hits.append({"type": "MACD_BULLISH", "signal": "BUY", "strength": "MODERATE",
                             "message": "MACD bullish crossover"})
            elif pm >= ps and cm < cs:
                hits.append({"type": "MACD_BEARISH", "signal": "SELL", "strength": "MODERATE",
                             "message": "MACD bearish crossover"})

    bu, bl, cc = _f(cur["bollinger_upper"]), _f(cur["bollinger_lower"]), _f(cur["close"])
    if None not in (bu, bl, cc):
        if cc <= bl:
            hits.append({"type": "BOLLINGER_LOWER", "signal": "BUY", "strength": "MODERATE",
                         "message": "At lower Bollinger band"})
        elif cc >= bu:
            hits.append({"type": "BOLLINGER_UPPER", "signal": "SELL", "strength": "MODERATE",
                         "message": "At upper Bollinger band"})

    if len(rows) >= 5:
        trailing = [r["volume"] for r in rows[1:5] if r["volume"] is not None]
        if trailing and cur["volume"] and cur["volume"] > (sum(trailing) / len(trailing)) * 2:
            hits.append({"type": "VOLUME_SPIKE", "signal": "WATCH", "strength": "MODERATE",
                         "message": f"Volume spike — {int(cur['volume']):,}"})
    return hits


def _verdict(hits: list[dict]) -> str:
    buys = sum(1 for h in hits if h["signal"] == "BUY")
    sells = sum(1 for h in hits if h["signal"] == "SELL")
    if buys > sells:
        return "BUY"
    if sells > buys:
        return "SELL"
    if hits:
        return "WATCH"
    return "NEUTRAL"


def signal_for_stock(stock_id: int) -> dict | None:
    with get_cursor() as cur:
        cur.execute(_RECENT_SQL, (stock_id,))
        rows = [dict(r) for r in cur.fetchall()]
    if not rows:
        return None
    latest = rows[0]
    hits = _rule_hits(rows)
    return {
        "date": latest["date"].isoformat() if latest["date"] else None,
        "close": _f(latest["close"]),
        "rsi_14": _f(latest["rsi_14"]),
        "macd": _f(latest["macd"]),
        "macd_signal": _f(latest["macd_signal"]),
        "macd_histogram": _f(latest["macd_histogram"]),
        "sma_20": _f(latest["sma_20"]),
        "sma_50": _f(latest["sma_50"]),
        "sma_200": _f(latest["sma_200"]),
        "verdict": _verdict(hits),
        "signals": hits,
    }
