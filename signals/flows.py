"""Pillar 3 — Flow & sentiment, split into MACRO (market-wide) and STOCK-specific.

- compute_macro_flows(conn): market-wide signals identical for every stock (FII/DII flow +
  streak, VIX, PCR, India Fear & Greed, Nifty breadth). Cached per calendar day so the 98-stock
  run computes it once. Returns point-items prefixed [MACRO].
- compute_stock_flows(conn, stock_id): signals unique to one stock (insider, bulk, SAST, 13F,
  MF/DII & FII% ownership QoQ, analyst target/upside, Google Trends). Items prefixed [STOCK].

score_flows() combines both around a neutral 50 base into the pillar result; the reasoning
lines carry [MACRO]/[STOCK] prefixes so the UI can render two sub-sections.
"""
from datetime import date

from .util import dict_cur, f, PillarResult

# per-day cache: {date_iso: macro_result}
_MACRO_CACHE: dict = {}


def compute_macro_flows(conn) -> dict:
    """Market-wide flow/sentiment signals (same for all stocks). Cached per day.

    Returns {"items": [(points, text, icon), ...], "key_metrics": {}, "contrary": [...]}.
    """
    key = date.today().isoformat()
    if key in _MACRO_CACHE:
        return _MACRO_CACHE[key]

    items: list[tuple] = []
    metrics: dict = {}
    contrary: list[str] = []

    with dict_cur(conn) as cur:
        # FII/DII 5-day cumulative + streak
        cur.execute("SELECT fii_net, dii_net FROM fii_dii_flows ORDER BY date DESC LIMIT 10")
        fii_rows = [dict(x) for x in cur.fetchall()]
        # India Fear & Greed
        cur.execute("SELECT value FROM macro_indicators WHERE market='IN' "
                    "AND indicator='india_fear_greed_index' ORDER BY date DESC LIMIT 2")
        fg = [f(x["value"]) for x in cur.fetchall()]
        # VIX + PCR
        cur.execute("SELECT india_vix, total_pcr FROM fno_data ORDER BY date DESC LIMIT 1")
        fno = cur.fetchone()
        # Nifty breadth — % of NSE watchlist stocks with latest close > latest SMA50
        cur.execute(
            """
            WITH latest AS (
                SELECT DISTINCT ON (ti.stock_id) ti.stock_id, ti.sma_50,
                       (SELECT close FROM daily_prices dp WHERE dp.stock_id=ti.stock_id
                        ORDER BY dp.date DESC LIMIT 1) AS close
                FROM technical_indicators ti
                JOIN stocks s ON s.id=ti.stock_id AND s.exchange='NSE'
                ORDER BY ti.stock_id, ti.date DESC
            )
            SELECT COUNT(*) FILTER (WHERE close > sma_50) above, COUNT(*) tot
            FROM latest WHERE sma_50 IS NOT NULL AND close IS NOT NULL
            """)
        br = cur.fetchone()

    # ── FII/DII ──
    if fii_rows:
        first = f(fii_rows[0]["fii_net"])
        streak = 0
        if first is not None and first != 0:
            for row in fii_rows:
                v = f(row["fii_net"])
                if v is None or v == 0 or (v > 0) != (first > 0):
                    break
                streak += 1
        cum5 = sum(f(x["fii_net"]) for x in fii_rows[:5] if f(x["fii_net"]) is not None)
        dcum5 = sum(f(x["dii_net"]) for x in fii_rows[:5] if f(x["dii_net"]) is not None)
        metrics["fii_5d_cum_cr"] = round(cum5, 0)
        metrics["dii_5d_cum_cr"] = round(dcum5, 0)
        if first is not None and first > 0:
            items.append((6 if streak >= 3 else 3, f"FII net buying across NSE: ₹{cum5:+,.0f}Cr (5d cumulative"
                          + (f", {streak}-day streak)" if streak >= 3 else ")"), "✅"))
        elif first is not None and first < 0:
            items.append((-6 if streak >= 3 else -3, f"FII net selling across NSE: ₹{cum5:+,.0f}Cr (5d cumulative"
                          + (f", {streak}-day streak)" if streak >= 3 else ")"), "❌"))
            if streak >= 3:
                contrary.append("Broad-market FII selling streak")
        # DII counter-flow context
        if dcum5:
            items.append((0, f"DII net {('buying' if dcum5 > 0 else 'selling')} across NSE: ₹{dcum5:+,.0f}Cr (5d)", "ℹ️"))

    # ── India Fear & Greed ──
    if fg and fg[0] is not None:
        v = fg[0]
        metrics["india_fear_greed"] = round(v, 0)
        label = ("Extreme Fear" if v < 25 else "Fear" if v < 45 else "Neutral" if v < 55
                 else "Greed" if v < 75 else "Extreme Greed")
        if v < 25:
            items.append((5, f"India Fear & Greed {v:.0f} — {label} (contrarian buy zone)", "✅"))
        elif v > 75:
            items.append((-5, f"India Fear & Greed {v:.0f} — {label} (frothy)", "⚠️"))
            contrary.append("Market greed elevated — froth risk")
        else:
            items.append((0, f"India Fear & Greed {v:.0f} — {label}", "ℹ️"))

    # ── VIX ──
    if fno and f(fno["india_vix"]) is not None:
        vix = f(fno["india_vix"])
        metrics["india_vix"] = round(vix, 1)
        if vix > 20:
            items.append((-3, f"VIX {vix:.1f} — elevated volatility / risk-off", "⚠️"))
        else:
            items.append((0, f"VIX {vix:.1f} — low volatility", "ℹ️"))

    # ── PCR ──
    if fno and f(fno["total_pcr"]) is not None:
        pcr = f(fno["total_pcr"])
        metrics["total_pcr"] = round(pcr, 2)
        if pcr > 1.2:
            items.append((4, f"PCR {pcr:.2f} — options positioned bullish", "✅"))
        elif pcr < 0.7:
            items.append((-4, f"PCR {pcr:.2f} — options positioned bearish", "❌"))
        else:
            items.append((0, f"PCR {pcr:.2f} — balanced positioning", "ℹ️"))

    # ── Nifty breadth ──
    if br and (br["tot"] or 0) > 0:
        pct = 100.0 * (br["above"] or 0) / br["tot"]
        metrics["breadth_above_sma50_pct"] = round(pct, 0)
        if pct >= 60:
            items.append((4, f"Breadth strong — {pct:.0f}% of NSE names above SMA50", "✅"))
        elif pct <= 40:
            items.append((-4, f"Breadth weak — only {pct:.0f}% of NSE names above SMA50", "❌"))
            contrary.append("Weak market breadth")
        else:
            items.append((0, f"Breadth neutral — {pct:.0f}% of NSE names above SMA50", "ℹ️"))

    result = {"items": items, "key_metrics": metrics, "contrary": contrary}
    _MACRO_CACHE[key] = result
    return result


def compute_stock_flows(conn, stock_id: int) -> dict:
    """Stock-specific flow/sentiment signals. Returns items prefixed [STOCK] downstream."""
    items: list[tuple] = []
    metrics: dict = {}
    contrary: list[str] = []
    with dict_cur(conn) as cur:
        cur.execute("SELECT tradingsymbol, exchange FROM stocks WHERE id=%s", (stock_id,))
        s = cur.fetchone()
        symbol = s["tradingsymbol"] if s else None
        india = s and s["exchange"] in ("NSE", "BSE")

        cur.execute("SELECT transaction, COUNT(*) n, COALESCE(SUM(quantity),0) qty FROM insider_trades "
                    "WHERE stock_id=%s AND date >= CURRENT_DATE - 30 GROUP BY transaction", (stock_id,))
        ins = {r["transaction"]: r for r in cur.fetchall()}

        cur.execute("SELECT transaction, COUNT(*) n FROM bulk_deals WHERE stock_id=%s "
                    "AND date >= CURRENT_DATE - 30 GROUP BY transaction", (stock_id,))
        bulk = {r["transaction"]: r["n"] for r in cur.fetchall()}

        cur.execute("SELECT transaction_type, pct_acquired FROM sast_disclosures WHERE stock_id=%s "
                    "AND disclosure_date >= CURRENT_DATE - 90 ORDER BY disclosure_date DESC LIMIT 1", (stock_id,))
        sast = cur.fetchone()

        us_13f = None
        if not india and symbol:
            cur.execute("SELECT COALESCE(SUM(qoq_change_shares),0) net, COUNT(*) n FROM institutional_holdings_13f "
                        "WHERE UPPER(symbol)=UPPER(%s) AND quarter=(SELECT MAX(quarter) FROM institutional_holdings_13f)", (symbol,))
            us_13f = cur.fetchone()

        # Shareholding FII% + DII% QoQ (last 2 quarters)
        cur.execute("SELECT fii_pct, dii_pct FROM shareholding_pattern WHERE stock_id=%s "
                    "ORDER BY quarter_end DESC LIMIT 2", (stock_id,))
        sh = [dict(x) for x in cur.fetchall()]

        # MF ownership MoM
        cur.execute("SELECT mom_change_pct FROM mf_stock_holdings WHERE stock_id=%s ORDER BY month DESC LIMIT 1", (stock_id,))
        mf = cur.fetchone()

        # Analyst target/upside
        cur.execute("SELECT consensus_rating, upside_pct, avg_target_price FROM analyst_targets "
                    "WHERE stock_id=%s ORDER BY date DESC LIMIT 1", (stock_id,))
        an = cur.fetchone()

        # News sentiment 7d + prior week
        cur.execute("SELECT AVG(sentiment_score) a, COUNT(*) n FROM news_sentiment WHERE stock_id=%s "
                    "AND date >= CURRENT_DATE - 7 AND sentiment_score IS NOT NULL", (stock_id,))
        n7 = cur.fetchone()

        # Google Trends
        cur.execute("SELECT value FROM macro_indicators WHERE indicator=%s ORDER BY date DESC LIMIT 2",
                    (f"google_trends_{symbol}",))
        gt = [f(x["value"]) for x in cur.fetchall()]

    buys = int(ins.get("BUY", {}).get("n", 0)) if "BUY" in ins else 0
    sells = int(ins.get("SELL", {}).get("n", 0)) if "SELL" in ins else 0
    if buys or sells:
        metrics["insider_buys_30d"] = buys
        metrics["insider_sells_30d"] = sells
        if buys > sells:
            qty = int(ins.get("BUY", {}).get("qty", 0) or 0)
            items.append((12, f"Insider buying — {buys} buy vs {sells} sell (30d"
                          + (f", {qty:,} sh)" if qty else ")"), "✅"))
        elif sells > buys:
            items.append((-6, f"Insider selling — {sells} sell vs {buys} buy (30d)", "❌"))
    else:
        items.append((0, "No insider transactions in last 30 days", "⚠️"))

    if bulk.get("BUY", 0) > bulk.get("SELL", 0):
        items.append((6, f"Bulk-deal accumulation ({bulk.get('BUY',0)} buys, 30d)", "✅"))
    elif bulk.get("SELL", 0) > bulk.get("BUY", 0):
        items.append((-5, f"Bulk-deal selling ({bulk.get('SELL',0)} sells, 30d)", "❌"))
    else:
        items.append((0, "No bulk deals in last 30 days", "⚠️"))

    if sast and (sast["transaction_type"] or "").upper().find("ACQ") >= 0:
        pct = f(sast["pct_acquired"])
        items.append((10, f"SAST acquisition disclosed{f' ({pct:.1f}%)' if pct else ''} — strategic buyer", "✅"))

    if us_13f and int(us_13f["n"] or 0) > 0:
        net = int(us_13f["net"] or 0)
        if net > 0:
            items.append((8, "13F: tracked funds net added shares last quarter", "✅"))
        elif net < 0:
            items.append((-6, "13F: tracked funds net reduced last quarter", "❌"))

    # FII% QoQ (shareholding)
    if len(sh) >= 2 and f(sh[0]["fii_pct"]) is not None and f(sh[1]["fii_pct"]) is not None:
        d = f(sh[0]["fii_pct"]) - f(sh[1]["fii_pct"])
        metrics["fii_pct"] = round(f(sh[0]["fii_pct"]), 2)
        if d > 0.3:
            items.append((6, f"FII ownership rose {d:+.1f}% QoQ ({f(sh[1]['fii_pct']):.1f}%→{f(sh[0]['fii_pct']):.1f}%)", "✅"))
        elif d < -0.3:
            items.append((-5, f"FII ownership fell {d:.1f}% QoQ ({f(sh[1]['fii_pct']):.1f}%→{f(sh[0]['fii_pct']):.1f}%)", "❌"))
    # DII/MF ownership QoQ (shareholding) + MF MoM
    if len(sh) >= 2 and f(sh[0]["dii_pct"]) is not None and f(sh[1]["dii_pct"]) is not None:
        d = f(sh[0]["dii_pct"]) - f(sh[1]["dii_pct"])
        if d > 0.3:
            items.append((5, f"DII/MF ownership rose {d:+.1f}% QoQ — domestic accumulation", "✅"))
        elif d < -0.3:
            items.append((-4, f"DII/MF ownership fell {d:.1f}% QoQ", "❌"))
    elif mf and f(mf["mom_change_pct"]) is not None:
        d = f(mf["mom_change_pct"])
        if abs(d) > 0.3:
            items.append((5 if d > 0 else -4, f"MF/DII ownership {'rising' if d>0 else 'falling'} ({d:+.1f}% MoM)",
                          "✅" if d > 0 else "❌"))

    # Analyst
    if an:
        up = f(an["upside_pct"])
        rating = (an["consensus_rating"] or "").upper()
        tgt = f(an["avg_target_price"])
        if up is not None:
            metrics["analyst_upside_pct"] = round(up, 1)
        if rating in ("STRONG_BUY", "BUY") and (up or 0) > 10:
            items.append((8, f"Analyst consensus {rating.replace('_',' ')}, avg target "
                          + (f"₹{tgt:,.0f} " if tgt else "") + f"({up:+.0f}% upside)", "✅"))
        elif rating in ("SELL", "STRONG_SELL"):
            items.append((-8, f"Analyst consensus {rating.replace('_',' ')}"
                          + (f", {up:+.0f}% upside" if up is not None else ""), "❌"))
        elif rating:
            items.append((0, f"Analyst consensus {rating.replace('_',' ')}"
                          + (f" ({up:+.0f}% upside)" if up is not None else ""), "ℹ️"))

    # News sentiment (stock-specific, from our DB)
    if n7 and n7["a"] is not None:
        a = f(n7["a"])
        metrics["news_sentiment_7d"] = round(a, 2)
        if a > 0.15:
            items.append((6, f"News sentiment positive ({a:+.2f}, {int(n7['n'])} stories, 7d)", "✅"))
        elif a < -0.15:
            items.append((-6, f"News sentiment negative ({a:+.2f}, {int(n7['n'])} stories, 7d)", "❌"))

    # Google Trends
    if len(gt) >= 2 and gt[0] is not None and gt[1] is not None and gt[0] > gt[1] * 1.2:
        items.append((3, "Search interest rising — retail attention building", "✅"))

    return {"items": items, "key_metrics": metrics, "contrary": contrary}


def score_flows(conn, stock_id: int) -> dict:
    """Combine MACRO (market-wide, cached) + STOCK-specific into the flows pillar result."""
    r = PillarResult()
    macro = compute_macro_flows(conn)
    stock = compute_stock_flows(conn, stock_id)

    for pts, text, icon in macro["items"]:
        r.add(pts, f"[MACRO] {text}", icon=icon)
    for pts, text, icon in stock["items"]:
        r.add(pts, f"[STOCK] {text}", icon=icon)

    r.key_metrics.update(macro["key_metrics"])
    r.key_metrics.update(stock["key_metrics"])
    for c in macro["contrary"] + stock["contrary"]:
        if c not in r.contrary:
            r.contrary.append(c)
    return r.finalize()
