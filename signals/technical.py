"""Pillar 1 — Technical signals (trend, RSI, MACD, Bollinger, volume, OBV, VWAP)."""
from .util import dict_cur, f, PillarResult

_SQL = """
    SELECT dp.date, dp.close, dp.volume,
           ti.rsi_14, ti.sma_20, ti.sma_50, ti.sma_200,
           ti.macd, ti.macd_signal, ti.macd_histogram,
           ti.bollinger_upper, ti.bollinger_lower,
           ti.volume_ratio, ti.volume_trend, ti.obv, ti.vwap
    FROM daily_prices dp
    LEFT JOIN technical_indicators ti
      ON dp.stock_id = ti.stock_id AND dp.date = ti.date
    WHERE dp.stock_id = %s
    ORDER BY dp.date DESC
    LIMIT 10
"""


def score_technical(conn, stock_id: int) -> dict:
    with dict_cur(conn) as cur:
        cur.execute(_SQL, (stock_id,))
        rows = [dict(r) for r in cur.fetchall()]
    r = PillarResult()
    if not rows:
        return r.finalize()

    cur_row = rows[0]
    prev = rows[1] if len(rows) > 1 else None
    close = f(cur_row["close"])
    sma20, sma50, sma200 = f(cur_row["sma_20"]), f(cur_row["sma_50"]), f(cur_row["sma_200"])
    rsi = f(cur_row["rsi_14"])

    # ── Trend (SMA alignment) ──
    if close and sma200:
        if close > sma200:
            r.add(8, f"Price above SMA200 ({close:.0f} > {sma200:.0f}) — long-term uptrend")
        else:
            r.add(-8, f"Price below SMA200 ({close:.0f} < {sma200:.0f}) — long-term downtrend")
    if sma50 and sma200:
        if sma50 > sma200:
            r.add(6, "Golden alignment — SMA50 above SMA200")
        else:
            r.add(-6, "Death alignment — SMA50 below SMA200")
    if close and sma20 and sma50 and sma200 and close > sma20 > sma50 > sma200:
        r.add(4, "Textbook uptrend stack: price > SMA20 > SMA50 > SMA200", icon="✅")
    if close and sma20:
        r.metric("price_vs_sma20_pct", round((close / sma20 - 1) * 100, 1))

    # ── RSI ──
    if rsi is not None:
        r.metric("rsi_14", round(rsi, 1))
        if rsi < 30:
            r.add(14, f"RSI {rsi:.0f} — oversold, mean-reversion buy zone")
        elif rsi < 45:
            r.add(5, f"RSI {rsi:.0f} — below midline, mild upside room")
        elif rsi <= 55:
            r.note(f"RSI {rsi:.0f} — neutral")
        elif rsi <= 70:
            r.add(-5, f"RSI {rsi:.0f} — above midline, extended")
        else:
            r.add(-14, f"RSI {rsi:.0f} — overbought, pullback risk")
            r.contra("RSI overbought — near-term pullback risk")

    # ── MACD ──
    macd, sig, hist = f(cur_row["macd"]), f(cur_row["macd_signal"]), f(cur_row["macd_histogram"])
    if macd is not None and sig is not None:
        pm = f(prev["macd"]) if prev else None
        ps = f(prev["macd_signal"]) if prev else None
        crossed_up = pm is not None and ps is not None and pm <= ps and macd > sig
        crossed_dn = pm is not None and ps is not None and pm >= ps and macd < sig
        if crossed_up:
            r.add(12, "MACD bullish crossover today")
        elif crossed_dn:
            r.add(-12, "MACD bearish crossover today")
        elif macd > sig:
            r.add(6, "MACD above signal — positive momentum")
        else:
            r.add(-6, "MACD below signal — negative momentum")
        if hist is not None and prev is not None:
            ph = f(prev["macd_histogram"])
            if ph is not None and abs(hist) > abs(ph) and hist > 0:
                r.add(3, "MACD histogram expanding — momentum building", icon="✅")

    # ── Bollinger ──
    bu, bl = f(cur_row["bollinger_upper"]), f(cur_row["bollinger_lower"])
    if close and bu and bl:
        if close <= bl and (rsi is None or rsi < 35):
            r.add(12, "At/below lower Bollinger band with weak RSI — strong buy setup")
        elif close >= bu and (rsi is None or rsi > 65):
            r.add(-12, "At/above upper Bollinger band with hot RSI — strong sell setup")
            r.contra("Stretched above upper Bollinger band")

    # ── Volume confirmation ──
    vr = f(cur_row["volume_ratio"])
    up_day = prev is not None and close is not None and f(prev["close"]) is not None and close >= f(prev["close"])
    if vr is not None:
        r.metric("volume_ratio", round(vr, 2))
        if vr > 2 and up_day:
            r.add(8, f"Volume {vr:.1f}x average on an up day — buying conviction")
        elif vr > 2 and not up_day:
            r.add(-8, f"Volume {vr:.1f}x average on a down day — distribution")
        elif vr < 0.5:
            r.note(f"Volume {vr:.1f}x average — thin, move may not sustain", icon="⚠️")

    # ── OBV trend (accumulation/distribution) ──
    obvs = [f(x["obv"]) for x in rows if f(x["obv"]) is not None]
    if len(obvs) >= 5:
        if obvs[0] > obvs[4]:
            r.add(4, "OBV rising — accumulation")
        elif obvs[0] < obvs[4]:
            r.add(-4, "OBV falling — distribution")

    # ── VWAP ──
    vwap = f(cur_row["vwap"])
    if close and vwap:
        if close > vwap:
            r.add(3, "Price above 20d VWAP — buyers in control")
        else:
            r.add(-3, "Price below 20d VWAP — sellers in control")

    return r.finalize()
