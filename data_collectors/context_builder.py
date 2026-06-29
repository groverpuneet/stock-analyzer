"""
data_collectors/context_builder.py  (Session H — Telegram bot data layer)

Single source of DB queries for the Telegram bot. Three consumers:
  1. The daily digest (telegram_daily_digest Dagster asset)
  2. Rule-based commands (/top5, /fear, /macro, ...)  — instant, no AI
  3. AI natural-language queries — build_context() assembles a compact (<2000 token)
     context block from only the rows relevant to the question, which is then handed
     to Gemini/Groq.

Ground rule: read-only, public market data only. No portfolio / holdings / P&L /
positions are ever queried here, and the AI system prompt forbids personalised advice.
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import get_conn

WATCHLIST = "Default"


# ----------------------------------------------------------------------------- helpers
def _rows(sql, params=()):
    conn = get_conn(); cur = conn.cursor()
    cur.execute(sql, params)
    cols = [c[0] for c in cur.description]
    out = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close(); conn.close()
    return out


def _one(sql, params=()):
    r = _rows(sql, params)
    return r[0] if r else None


def _f(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def fg_rating(score):
    if score is None:
        return None
    return ("Extreme Fear" if score < 25 else "Fear" if score < 45 else
            "Neutral" if score < 55 else "Greed" if score < 75 else "Extreme Greed")


def resolve_symbol(token: str):
    """Resolve a user-typed token (e.g. 'sbin') to (id, tradingsymbol, name)."""
    token = (token or "").strip().upper()
    if not token:
        return None
    return _one(
        "SELECT id, tradingsymbol, name FROM stocks "
        "WHERE UPPER(tradingsymbol) = %s ORDER BY (exchange='NSE') DESC LIMIT 1",
        (token,),
    )


def extract_symbols(message: str, limit: int = 4):
    """Find watchlist/known tickers mentioned in a free-text query."""
    cleaned = "".join(c if c.isalnum() or c.isspace() else " " for c in message.upper())
    words = {w for w in cleaned.split() if len(w) >= 3}
    if not words:
        return []
    hits = _rows(
        "SELECT DISTINCT ON (UPPER(tradingsymbol)) id, tradingsymbol, name "
        "FROM stocks WHERE UPPER(tradingsymbol) = ANY(%s) "
        "ORDER BY UPPER(tradingsymbol), (exchange='NSE') DESC",
        (list(words),),
    )
    return hits[:limit]


# ----------------------------------------------------------------------------- market-wide
def get_fear_greed():
    out = {}
    for key, market, indicator in (("india", "IN", "india_fear_greed_index"),
                                   ("us", "US", "us_fear_greed_index")):
        latest = _one(
            "SELECT date, value FROM macro_indicators "
            "WHERE market=%s AND indicator=%s ORDER BY date DESC LIMIT 1",
            (market, indicator),
        )
        prev = _one(
            "SELECT value FROM macro_indicators "
            "WHERE market=%s AND indicator=%s ORDER BY date DESC OFFSET 1 LIMIT 1",
            (market, indicator),
        )
        score = _f(latest["value"]) if latest else None
        prev_v = _f(prev["value"]) if prev else None
        trend = "→"
        if score is not None and prev_v is not None:
            trend = "↑" if score > prev_v + 0.5 else "↓" if score < prev_v - 0.5 else "→"
        out[key] = {"score": score, "rating": fg_rating(score), "trend": trend,
                    "date": latest["date"] if latest else None}
    return out


def get_fii_dii():
    return _one(
        "SELECT date, fii_buy, fii_sell, fii_net, dii_buy, dii_sell, dii_net "
        "FROM fii_dii_flows ORDER BY date DESC LIMIT 1"
    )


def get_macro_snapshot():
    fno = _one("SELECT date, india_vix, index_pcr, total_pcr, max_pain "
               "FROM fno_data ORDER BY date DESC LIMIT 1")
    rates = _rows(
        "SELECT DISTINCT ON (indicator) indicator, value, unit, period "
        "FROM macro_indicators WHERE market='IN' "
        "AND indicator IN ('repo_rate','crr','slr','usd_inr','wpi_inflation',"
        "'cpi_inflation','gdp_growth_yoy','forex_reserves_total','bank_credit_growth_yoy') "
        "ORDER BY indicator, date DESC"
    )
    return {"fno": fno, "rates": {r["indicator"]: r for r in rates},
            "fii_dii": get_fii_dii()}


# ----------------------------------------------------------------------------- signals / scores
def get_top_signals(n: int = 5, exchange: str = "NSE"):
    """Top watchlist stocks by composite_score (latest model run)."""
    return _rows(
        """
        SELECT s.tradingsymbol AS symbol, s.name, sc.composite_score,
               sc.momentum_score, sc.rsi_rank
        FROM stock_scores sc
        JOIN stocks s ON sc.stock_id = s.id
        JOIN watchlist w ON w.stock_id = s.id
        WHERE w.name = %s AND s.exchange = %s
          AND sc.date = (SELECT MAX(date) FROM stock_scores)
          AND sc.composite_score IS NOT NULL
        ORDER BY sc.composite_score DESC
        LIMIT %s
        """,
        (WATCHLIST, exchange, n),
    )


def get_watchlist_scores(exchange: str = "NSE"):
    return _rows(
        """
        SELECT s.tradingsymbol AS symbol, sc.composite_score, sc.momentum_score
        FROM stock_scores sc
        JOIN stocks s ON sc.stock_id = s.id
        JOIN watchlist w ON w.stock_id = s.id
        WHERE w.name = %s AND s.exchange = %s
          AND sc.date = (SELECT MAX(date) FROM stock_scores)
        ORDER BY sc.composite_score DESC NULLS LAST
        """,
        (WATCHLIST, exchange),
    )


def get_signal_detail(symbol: str):
    """Latest price + indicators + a coarse verdict for one stock."""
    st = resolve_symbol(symbol)
    if not st:
        return None
    px = _one(
        """
        SELECT dp.date, dp.close, dp.volume,
               ti.rsi_14, ti.sma_20, ti.sma_50, ti.sma_200,
               ti.macd, ti.macd_signal, ti.bollinger_upper, ti.bollinger_lower
        FROM daily_prices dp
        LEFT JOIN technical_indicators ti
          ON dp.stock_id = ti.stock_id AND dp.date = ti.date
        WHERE dp.stock_id = %s ORDER BY dp.date DESC LIMIT 1
        """,
        (st["id"],),
    )
    score = _one(
        "SELECT composite_score, momentum_score, rsi_rank, macd_rank "
        "FROM stock_scores WHERE stock_id=%s ORDER BY date DESC LIMIT 1",
        (st["id"],),
    )
    verdict = "NEUTRAL"
    if px:
        rsi = _f(px["rsi_14"])
        close, s200 = _f(px["close"]), _f(px["sma_200"])
        bull = bear = 0
        if rsi is not None:
            if rsi < 30:
                bull += 1
            elif rsi > 70:
                bear += 1
        if close and s200:
            if close > s200:
                bull += 1
            else:
                bear += 1
        verdict = "BUY" if bull > bear else "SELL" if bear > bull else "WATCH" if px else "NEUTRAL"
    return {"stock": st, "px": px, "score": score, "verdict": verdict}


# ----------------------------------------------------------------------------- fundamentals / insider / news
def get_fundamentals(symbol: str):
    st = resolve_symbol(symbol)
    if not st:
        return None
    f = _one(
        "SELECT date, market_cap, pe_ratio, pb_ratio, roe, roce_pct, debt_to_equity, "
        "eps, dividend_yield_pct, promoter_holding_pct, pledged_pct "
        "FROM fundamentals WHERE stock_id=%s AND source <> 'screener_pe_history' "
        "ORDER BY date DESC LIMIT 1",
        (st["id"],),
    )
    return {"stock": st, "fundamentals": f}


def get_insider(symbol: str, days: int = 60, limit: int = 8):
    st = resolve_symbol(symbol)
    if not st:
        return None
    trades = _rows(
        "SELECT date, person_name, person_category, transaction, quantity, price "
        "FROM insider_trades WHERE stock_id=%s AND date >= CURRENT_DATE - %s "
        "ORDER BY date DESC LIMIT %s",
        (st["id"], days, limit),
    )
    return {"stock": st, "trades": trades}


def get_top_news(n: int = 10, days: int = 1):
    # Dedupe by headline: the proactive news collector can tag one wire story to
    # several tickers, so keep the single best-scored (symbol, headline) per headline.
    return _rows(
        """
        SELECT symbol, headline, sentiment, sentiment_score, source, date FROM (
            SELECT DISTINCT ON (ns.headline)
                   s.tradingsymbol AS symbol, ns.headline, ns.sentiment,
                   ns.sentiment_score, ns.source, ns.date
            FROM news_sentiment ns
            JOIN stocks s ON ns.stock_id = s.id
            WHERE ns.date >= CURRENT_DATE - %s AND ns.sentiment_score IS NOT NULL
            ORDER BY ns.headline, ABS(ns.sentiment_score) DESC
        ) d
        ORDER BY ABS(d.sentiment_score) DESC, d.date DESC
        LIMIT %s
        """,
        (days, n),
    )


# ----------------------------------------------------------------------------- earnings / risk / 13F
def get_upcoming_earnings(days: int = 14):
    return _rows(
        """
        SELECT DISTINCT ON (s.tradingsymbol) s.tradingsymbol AS symbol, e.results_date, e.quarter
        FROM earnings_calendar e
        JOIN stocks s ON e.stock_id = s.id
        WHERE e.results_date BETWEEN CURRENT_DATE AND CURRENT_DATE + %s
        ORDER BY s.tradingsymbol, e.results_date
        """,
        (days,),
    )


def get_risk_alerts(limit: int = 8):
    """Compose risk alerts from public market data — pledge rises, below-SMA200, bad news."""
    alerts = []
    for r in _rows(
        "SELECT s.tradingsymbol AS symbol, p.current_pledge_pct, p.change_pct, p.alert_type "
        "FROM pledging_alerts p JOIN stocks s ON p.stock_id=s.id "
        "WHERE p.resolved = false ORDER BY p.change_pct DESC NULLS LAST LIMIT 5"
    ):
        ch = _f(r["change_pct"])
        alerts.append(f"{r['symbol']} pledge {r['alert_type'] or 'change'}"
                      + (f" (+{ch:.1f}pp)" if ch else ""))
    for r in _rows(
        """
        SELECT s.tradingsymbol AS symbol
        FROM watchlist w JOIN stocks s ON w.stock_id=s.id
        JOIN technical_indicators ti ON ti.stock_id=s.id
          AND ti.date=(SELECT MAX(date) FROM technical_indicators t WHERE t.stock_id=s.id)
        JOIN daily_prices dp ON dp.stock_id=s.id AND dp.date=ti.date
        WHERE w.name=%s AND s.exchange='NSE'
          AND ti.sma_200 IS NOT NULL AND dp.close < ti.sma_200
        ORDER BY s.tradingsymbol
        """,
        (WATCHLIST,),
    ):
        alerts.append(f"{r['symbol']} below SMA200")
    for r in _rows(
        """
        SELECT s.tradingsymbol AS symbol, ns.sentiment_score
        FROM news_sentiment ns JOIN stocks s ON ns.stock_id=s.id
        JOIN watchlist w ON w.stock_id=s.id
        WHERE w.name=%s AND ns.date >= CURRENT_DATE - 7
          AND ns.sentiment_score <= -0.5
        ORDER BY ns.sentiment_score ASC LIMIT 3
        """,
        (WATCHLIST,),
    ):
        alerts.append(f"{r['symbol']} negative news ({_f(r['sentiment_score']):.2f})")
    return alerts[:limit]


def get_13f_holdings(filer_query: str = "Berkshire", limit: int = 10):
    rows = _rows(
        """
        SELECT tf.filer_name, h.symbol, h.issuer_name, h.market_value_usd,
               h.pct_of_portfolio, h.qoq_change_pct, h.quarter
        FROM institutional_holdings_13f h
        JOIN tracked_filers tf ON h.filer_cik = tf.filer_cik
        WHERE tf.filer_name ILIKE %s
          AND h.quarter = (SELECT MAX(quarter) FROM institutional_holdings_13f h2
                           WHERE h2.filer_cik = h.filer_cik)
        ORDER BY h.market_value_usd DESC NULLS LAST
        LIMIT %s
        """,
        (f"%{filer_query}%", limit),
    )
    return rows


# ----------------------------------------------------------------------------- AI context
def build_context(message: str) -> str:
    """Assemble a compact context block (<~2000 tokens) for an AI query."""
    parts = []

    fg = get_fear_greed()
    if fg["india"]["score"] is not None or fg["us"]["score"] is not None:
        parts.append(
            "FEAR&GREED: India "
            f"{fg['india']['score']} ({fg['india']['rating']}) | "
            f"US {fg['us']['score']} ({fg['us']['rating']})"
        )
    macro = get_macro_snapshot()
    fno, rates, fii = macro["fno"], macro["rates"], macro["fii_dii"]
    if fno:
        parts.append(f"MACRO: VIX {_f(fno['india_vix'])} | PCR {_f(fno['total_pcr'])} | "
                     f"Repo {_f((rates.get('repo_rate') or {}).get('value'))}% | "
                     f"USDINR {_f((rates.get('usd_inr') or {}).get('value'))}")
    if fii:
        parts.append(f"FII/DII net (₹cr, {fii['date']}): FII {_f(fii['fii_net'])}, DII {_f(fii['dii_net'])}")

    symbols = extract_symbols(message)
    if symbols:
        for st in symbols:
            sym = st["tradingsymbol"]
            d = get_signal_detail(sym)
            if d and d["px"]:
                px, sc = d["px"], d["score"] or {}
                parts.append(
                    f"STOCK {sym} ({st['name']}): verdict={d['verdict']}, close={_f(px['close'])}, "
                    f"RSI14={_f(px['rsi_14'])}, MACD={_f(px['macd'])}/{_f(px['macd_signal'])}, "
                    f"SMA50={_f(px['sma_50'])}, SMA200={_f(px['sma_200'])}, "
                    f"composite={_f(sc.get('composite_score'))}"
                )
            fd = get_fundamentals(sym)
            if fd and fd["fundamentals"]:
                f = fd["fundamentals"]
                parts.append("  FUNDAMENTALS " + sym + ": " + ", ".join(
                    f"{k}={_f(v) if not isinstance(v, str) else v}"
                    for k, v in f.items() if k != "date" and v is not None))
            ins = get_insider(sym, days=30, limit=5)
            if ins and ins["trades"]:
                parts.append("  INSIDER " + sym + ": " + "; ".join(
                    f"{t['date']} {t['transaction']} {t['quantity']} ({t['person_category'] or '?'})"
                    for t in ins["trades"]))
            news = _rows(
                "SELECT headline, sentiment, sentiment_score FROM news_sentiment "
                "WHERE stock_id=%s ORDER BY date DESC LIMIT 3", (st["id"],))
            if news:
                parts.append("  NEWS " + sym + ": " + " | ".join(
                    f"[{n['sentiment']} {_f(n['sentiment_score'])}] {n['headline']}" for n in news))
    else:
        top = get_top_signals(5)
        if top:
            parts.append("TOP BY SCORE: " + ", ".join(
                f"{t['symbol']} ({_f(t['composite_score'])})" for t in top))

    low = message.lower()
    if any(name.lower() in low for name in ("berkshire", "buffett", "bridgewater",
            "citadel", "renaissance", "pershing", "13f", "hedge fund")):
        filer = "Berkshire"
        for k in ("bridgewater", "citadel", "renaissance", "pershing"):
            if k in low:
                filer = k
        h = get_13f_holdings(filer, 8)
        if h:
            parts.append(f"13F {h[0]['filer_name']} top holdings: " + ", ".join(
                f"{r['symbol'] or r['issuer_name']} ${_f(r['market_value_usd'])/1e6:.0f}M "
                f"({_f(r['pct_of_portfolio'])}%)"
                for r in h))

    return "\n".join(parts) if parts else "No relevant rows found in the database."


if __name__ == "__main__":
    import json
    q = " ".join(sys.argv[1:]) or "Why is SBIN looking strong?"
    print("QUERY:", q)
    print("-" * 60)
    print(build_context(q))
