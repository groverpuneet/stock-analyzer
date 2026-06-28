"""Expanded dashboard — every available datum per watchlist stock, in one payload.

Joins price/technical/fundamental/score/sentiment/insider data per stock. The
frontend renders it as a sortable, filterable table. FII/DII is market-wide so
it's returned once at the top level (not per row).
"""
from fastapi import APIRouter

from db import query_all, query_one
from signals_engine import signal_for_stock

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _f(v):
    return float(v) if v is not None else None


@router.get("")
def dashboard(watchlist: str = "Default"):
    stocks = query_all(
        "SELECT s.id, s.tradingsymbol AS symbol, s.name, s.exchange, s.segment "
        "FROM watchlist w JOIN stocks s ON w.stock_id = s.id "
        "WHERE w.name = %s AND s.exchange = 'NSE' ORDER BY s.tradingsymbol",
        (watchlist,),
    )
    ids = [s["id"] for s in stocks]
    if not ids:
        return {"stocks": [], "fii_dii": None}

    # Prices: latest, previous, 52-week high/low
    prices = {r["stock_id"]: r for r in query_all(
        """
        SELECT stock_id,
               (array_agg(close ORDER BY date DESC))[1] AS close,
               (array_agg(close ORDER BY date DESC))[2] AS prev_close,
               MAX(high) FILTER (WHERE date >= CURRENT_DATE - INTERVAL '365 days') AS w52_high,
               MIN(low)  FILTER (WHERE date >= CURRENT_DATE - INTERVAL '365 days') AS w52_low
        FROM daily_prices WHERE stock_id = ANY(%s) GROUP BY stock_id
        """, (ids,))}

    tech = {r["stock_id"]: r for r in query_all(
        """
        SELECT DISTINCT ON (stock_id) stock_id, rsi_14, macd, macd_signal,
               sma_20, sma_50, sma_200, bollinger_upper, bollinger_lower
        FROM technical_indicators WHERE stock_id = ANY(%s) ORDER BY stock_id, date DESC
        """, (ids,))}

    # Full fundamentals (exclude the PE-history-only rows)
    fund = {r["stock_id"]: r for r in query_all(
        """
        SELECT DISTINCT ON (stock_id) stock_id, market_cap, pb_ratio, roe,
               debt_to_equity, roce_pct
        FROM fundamentals WHERE stock_id = ANY(%s) AND source <> 'screener_pe_history'
        ORDER BY stock_id, date DESC
        """, (ids,))}

    # Current P/E = latest point of the Screener chart series (same basis as the
    # percentile); fall back to any pe_ratio for stocks without seeded history.
    cur_pe = {r["stock_id"]: r["pe_ratio"] for r in query_all(
        """
        SELECT DISTINCT ON (stock_id) stock_id, pe_ratio
        FROM fundamentals WHERE stock_id = ANY(%s) AND source = 'screener_pe_history'
        AND pe_ratio IS NOT NULL ORDER BY stock_id, date DESC
        """, (ids,))}
    for r in query_all(
        """
        SELECT DISTINCT ON (stock_id) stock_id, pe_ratio
        FROM fundamentals WHERE stock_id = ANY(%s) AND pe_ratio IS NOT NULL
        ORDER BY stock_id, date DESC
        """, (ids,)):
        cur_pe.setdefault(r["stock_id"], r["pe_ratio"])

    scores = {r["stock_id"]: r for r in query_all(
        """
        SELECT DISTINCT ON (stock_id) stock_id, composite_score, rsi_rank,
               momentum_score, volume_rank, macd_rank, pe_percentile, data_completeness_score
        FROM stock_scores WHERE stock_id = ANY(%s) ORDER BY stock_id, date DESC
        """, (ids,))}

    news = {r["stock_id"]: r for r in query_all(
        """
        SELECT DISTINCT ON (stock_id) stock_id, sentiment, sentiment_score, date
        FROM news_sentiment WHERE stock_id = ANY(%s) ORDER BY stock_id, date DESC
        """, (ids,))}

    # Insider activity (last 30 days) — combine SEBI PIT + bulk deals
    insider = {r["stock_id"]: r for r in query_all(
        """
        SELECT stock_id,
               SUM(CASE WHEN transaction = 'BUY' THEN 1 ELSE 0 END) AS buys,
               SUM(CASE WHEN transaction = 'SELL' THEN 1 ELSE 0 END) AS sells
        FROM (
            SELECT stock_id, transaction FROM insider_trades
            WHERE stock_id = ANY(%s) AND date >= CURRENT_DATE - INTERVAL '30 days'
            UNION ALL
            SELECT stock_id, transaction FROM bulk_deals
            WHERE stock_id = ANY(%s) AND date >= CURRENT_DATE - INTERVAL '30 days'
        ) t GROUP BY stock_id
        """, (ids, ids))}

    out = []
    for s in stocks:
        sid = s["id"]
        p, t, f, sc, nw, ins = (prices.get(sid, {}), tech.get(sid, {}), fund.get(sid, {}),
                                scores.get(sid, {}), news.get(sid, {}), insider.get(sid, {}))
        close = _f(p.get("close"))
        prev = _f(p.get("prev_close"))
        day_change = round((close / prev - 1) * 100, 2) if close and prev else None
        bu, bl = _f(t.get("bollinger_upper")), _f(t.get("bollinger_lower"))
        bb_pos = round((close - bl) / (bu - bl) * 100, 1) if (close and bu and bl and bu > bl) else None
        sig = signal_for_stock(sid)
        buys, sells = int(ins.get("buys") or 0), int(ins.get("sells") or 0)
        out.append({
            "stock_id": sid, "symbol": s["symbol"], "name": s["name"],
            "verdict": sig["verdict"] if sig else "NEUTRAL",
            # price
            "close": close, "day_change_pct": day_change,
            "week52_high": _f(p.get("w52_high")), "week52_low": _f(p.get("w52_low")),
            # technical
            "rsi_14": _f(t.get("rsi_14")), "macd": _f(t.get("macd")),
            "macd_signal": _f(t.get("macd_signal")), "bb_position": bb_pos,
            "sma_20": _f(t.get("sma_20")), "sma_50": _f(t.get("sma_50")), "sma_200": _f(t.get("sma_200")),
            # fundamentals
            "pe_ratio": _f(cur_pe.get(sid)), "pe_percentile": _f(sc.get("pe_percentile")),
            "pb_ratio": _f(f.get("pb_ratio")), "roe": _f(f.get("roe")),
            "debt_to_equity": _f(f.get("debt_to_equity")), "market_cap": _f(f.get("market_cap")),
            # sentiment
            "sentiment": nw.get("sentiment"), "sentiment_score": _f(nw.get("sentiment_score")),
            # scores
            "composite_score": _f(sc.get("composite_score")), "rsi_rank": _f(sc.get("rsi_rank")),
            "momentum_score": _f(sc.get("momentum_score")), "volume_rank": _f(sc.get("volume_rank")),
            "macd_rank": _f(sc.get("macd_rank")),
            "completeness": _f(sc.get("data_completeness_score")),
            # insider
            "insider_buys": buys, "insider_sells": sells, "insider_net": buys - sells,
        })

    fii_dii = query_one(
        "SELECT date, fii_net, dii_net FROM fii_dii_flows ORDER BY date DESC LIMIT 1"
    )
    return {"stocks": out, "fii_dii": fii_dii}
