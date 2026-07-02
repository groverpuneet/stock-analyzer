"""Pillar 3 — Flow & sentiment (FII/DII, insider, bulk/SAST/13F/MF, options, news, trends)."""
from .util import dict_cur, f, PillarResult


def score_flows(conn, stock_id: int) -> dict:
    r = PillarResult()
    with dict_cur(conn) as cur:
        cur.execute("SELECT tradingsymbol, exchange FROM stocks WHERE id=%s", (stock_id,))
        s = cur.fetchone()
        symbol = s["tradingsymbol"] if s else None
        exchange = s["exchange"] if s else None
        india = exchange in ("NSE", "BSE")

        # Insider trades (last 30d)
        cur.execute(
            "SELECT transaction, COUNT(*) n, COALESCE(SUM(quantity),0) qty FROM insider_trades "
            "WHERE stock_id=%s AND date >= CURRENT_DATE - 30 GROUP BY transaction", (stock_id,))
        ins = {row["transaction"]: row for row in cur.fetchall()}

        # Bulk/block deals (last 30d)
        cur.execute(
            "SELECT transaction, COUNT(*) n FROM bulk_deals WHERE stock_id=%s "
            "AND date >= CURRENT_DATE - 30 GROUP BY transaction", (stock_id,))
        bulk = {row["transaction"]: row["n"] for row in cur.fetchall()}

        # SAST acquisitions (last 90d)
        cur.execute(
            "SELECT transaction_type, pct_acquired, disclosure_date FROM sast_disclosures "
            "WHERE stock_id=%s AND disclosure_date >= CURRENT_DATE - 90 "
            "ORDER BY disclosure_date DESC LIMIT 1", (stock_id,))
        sast = cur.fetchone()

        # MF ownership trend
        cur.execute(
            "SELECT ownership_pct, mom_change_pct FROM mf_stock_holdings WHERE stock_id=%s "
            "ORDER BY month DESC LIMIT 1", (stock_id,))
        mf = cur.fetchone()

        # News sentiment (7d avg + prior 7d for trend)
        cur.execute(
            "SELECT AVG(sentiment_score) a, COUNT(*) n FROM news_sentiment WHERE stock_id=%s "
            "AND date >= CURRENT_DATE - 7 AND sentiment_score IS NOT NULL", (stock_id,))
        n7 = cur.fetchone()
        cur.execute(
            "SELECT AVG(sentiment_score) a FROM news_sentiment WHERE stock_id=%s "
            "AND date >= CURRENT_DATE - 14 AND date < CURRENT_DATE - 7 AND sentiment_score IS NOT NULL", (stock_id,))
        n14 = cur.fetchone()

        # 13F (US) — top funds' QoQ change last quarter
        us_13f = None
        if not india and symbol:
            cur.execute(
                "SELECT COALESCE(SUM(qoq_change_shares),0) net, COUNT(*) n FROM institutional_holdings_13f "
                "WHERE UPPER(symbol)=UPPER(%s) AND quarter=(SELECT MAX(quarter) FROM institutional_holdings_13f)", (symbol,))
            us_13f = cur.fetchone()

        # Market-wide FII/DII (India) — streak + 5d cumulative
        fii_rows = []
        if india:
            cur.execute("SELECT fii_net, dii_net FROM fii_dii_flows ORDER BY date DESC LIMIT 10")
            fii_rows = [dict(x) for x in cur.fetchall()]

        # Options market context (India, market-wide)
        fno = None
        if india:
            cur.execute("SELECT total_pcr, india_vix FROM fno_data ORDER BY date DESC LIMIT 1")
            fno = cur.fetchone()

        # Google Trends (retail interest)
        cur.execute(
            "SELECT value, date FROM macro_indicators WHERE indicator=%s ORDER BY date DESC LIMIT 4",
            (f"google_trends_{symbol}",))
        gt = [dict(x) for x in cur.fetchall()]

    # ── Insider ──
    buys = int(ins.get("BUY", {}).get("n", 0)) if "BUY" in ins else 0
    sells = int(ins.get("SELL", {}).get("n", 0)) if "SELL" in ins else 0
    if buys or sells:
        r.metric("insider_buys_30d", buys)
        r.metric("insider_sells_30d", sells)
        if buys > sells:
            r.add(12, f"Insider buying — {buys} buy vs {sells} sell (30d)")
        elif sells > buys:
            r.add(-6, f"Insider selling — {sells} sell vs {buys} buy (30d)")

    # ── Bulk deals ──
    if bulk.get("BUY", 0) > bulk.get("SELL", 0):
        r.add(6, f"Bulk-deal accumulation ({bulk.get('BUY',0)} buys, 30d)")
    elif bulk.get("SELL", 0) > bulk.get("BUY", 0):
        r.add(-5, f"Bulk-deal selling ({bulk.get('SELL',0)} sells, 30d)")

    # ── SAST ──
    if sast and (sast["transaction_type"] or "").upper().find("ACQ") >= 0:
        pct = f(sast["pct_acquired"])
        r.add(10, f"SAST acquisition disclosed{f' ({pct:.1f}%)' if pct else ''} — strategic buyer")

    # ── 13F (US) ──
    if us_13f and int(us_13f["n"] or 0) > 0:
        net = int(us_13f["net"] or 0)
        if net > 0:
            r.add(8, f"13F: tracked funds net added shares last quarter")
        elif net < 0:
            r.add(-6, "13F: tracked funds net reduced last quarter")

    # ── MF ownership ──
    if mf and f(mf["mom_change_pct"]) is not None:
        d = f(mf["mom_change_pct"])
        if d > 0.3:
            r.add(5, f"MF/DII ownership rising (+{d:.1f}% MoM) — accumulation")
        elif d < -0.3:
            r.add(-4, f"MF/DII ownership falling ({d:.1f}% MoM)")

    # ── News sentiment ──
    if n7 and n7["a"] is not None:
        a = f(n7["a"])
        r.metric("news_sentiment_7d", round(a, 2))
        if a > 0.15:
            r.add(6, f"News sentiment positive ({a:+.2f}, {int(n7['n'])} stories, 7d)")
        elif a < -0.15:
            r.add(-6, f"News sentiment negative ({a:+.2f}, {int(n7['n'])} stories, 7d)")
        prev = f(n14["a"]) if n14 and n14["a"] is not None else None
        if prev is not None and a - prev > 0.2:
            r.add(3, "News sentiment improving vs prior week", icon="✅")
        elif prev is not None and a - prev < -0.2:
            r.add(-3, "News sentiment deteriorating vs prior week", icon="⚠️")

    # ── Market-wide FII/DII streak (India) ──
    if fii_rows:
        streak = 0
        for row in fii_rows:
            v = f(row["fii_net"])
            if v is None or v == 0:
                break
            if (v > 0) == (f(fii_rows[0]["fii_net"]) > 0):
                streak += 1
            else:
                break
        cum5 = sum(f(x["fii_net"]) for x in fii_rows[:5] if f(x["fii_net"]) is not None)
        r.metric("fii_5d_cum_cr", round(cum5, 0))
        first = f(fii_rows[0]["fii_net"])
        if first is not None and first > 0 and streak >= 3:
            r.add(6, f"FII net buying {streak} days straight (₹{cum5:+,.0f}Cr 5d)")
        elif first is not None and first < 0 and streak >= 3:
            r.add(-6, f"FII net selling {streak} days straight (₹{cum5:+,.0f}Cr 5d)")
            r.contra("Broad-market FII selling streak")

    # ── Options (India, market context) ──
    if fno:
        pcr = f(fno["total_pcr"])
        vix = f(fno["india_vix"])
        if pcr is not None:
            r.metric("total_pcr", round(pcr, 2))
            if pcr > 1.2:
                r.add(4, f"PCR {pcr:.2f} — options positioned bullish")
            elif pcr < 0.7:
                r.add(-4, f"PCR {pcr:.2f} — options positioned bearish")
        if vix is not None:
            r.metric("india_vix", round(vix, 1))

    # ── Google Trends ──
    if len(gt) >= 2 and f(gt[0]["value"]) is not None and f(gt[1]["value"]) is not None:
        if f(gt[0]["value"]) > f(gt[1]["value"]) * 1.2:
            r.add(3, "Search interest rising — retail attention building")

    return r.finalize()
