"""Fear & Greed Index API — dedicated endpoint for iPhone widget + external access."""
from fastapi import APIRouter

from db import query_all, query_one

router = APIRouter(prefix="/api", tags=["fear-greed"])


def _label(score):
    if score is None:
        return None
    if score < 25:
        return "Extreme Fear"
    if score < 45:
        return "Fear"
    if score < 55:
        return "Neutral"
    if score < 75:
        return "Greed"
    return "Extreme Greed"


def _direction(current, previous):
    if current is None or previous is None:
        return "flat"
    if current > previous:
        return "up"
    if current < previous:
        return "down"
    return "flat"


def _get_fg_data(market: str, indicator: str, history_limit: int = 30) -> dict:
    """Fetch Fear & Greed data for a market."""
    rows = query_all(
        """
        SELECT date, value FROM macro_indicators
        WHERE market = %s AND indicator = %s
        ORDER BY date DESC LIMIT %s
        """,
        (market, indicator, history_limit + 1),
    )

    if not rows:
        return {
            "score": None,
            "label": None,
            "date": None,
            "previous_score": None,
            "direction": "flat",
            "history": [],
        }

    latest = rows[0]
    previous = rows[1] if len(rows) > 1 else None

    score = float(latest["value"]) if latest["value"] is not None else None
    prev_score = float(previous["value"]) if previous and previous["value"] is not None else None

    history = [
        {"date": str(r["date"]), "score": float(r["value"]) if r["value"] is not None else None}
        for r in reversed(rows[:history_limit])
    ]

    return {
        "score": round(score, 1) if score is not None else None,
        "label": _label(score),
        "date": str(latest["date"]) if latest["date"] else None,
        "previous_score": round(prev_score, 1) if prev_score is not None else None,
        "direction": _direction(score, prev_score),
        "history": history,
    }


def _get_india_components() -> dict:
    """Get India F&G component values from latest data sources."""
    components = {}

    vix = query_one(
        "SELECT india_vix FROM fno_data WHERE india_vix IS NOT NULL ORDER BY date DESC LIMIT 1"
    )
    if vix:
        components["vix"] = float(vix["india_vix"])

    pcr = query_one(
        "SELECT index_pcr FROM fno_data WHERE index_pcr IS NOT NULL ORDER BY date DESC LIMIT 1"
    )
    if pcr:
        components["pcr"] = float(pcr["index_pcr"])

    fii = query_one(
        "SELECT fii_net FROM fii_dii_flows ORDER BY date DESC LIMIT 1"
    )
    if fii and fii["fii_net"] is not None:
        components["fii_flow"] = float(fii["fii_net"])

    pct_above_sma = query_one(
        """
        SELECT COUNT(*) FILTER (WHERE dp.close > ti.sma_50) * 100.0 / NULLIF(COUNT(*), 0) AS pct
        FROM daily_prices dp
        JOIN technical_indicators ti ON dp.stock_id = ti.stock_id AND dp.date = ti.date
        JOIN stocks s ON dp.stock_id = s.id
        WHERE s.market = 'IN' AND dp.date = (
            SELECT MAX(date) FROM daily_prices WHERE stock_id = dp.stock_id
        )
        """
    )
    if pct_above_sma and pct_above_sma["pct"] is not None:
        components["pct_above_sma50"] = round(float(pct_above_sma["pct"]), 1)

    pct_rsi = query_one(
        """
        SELECT COUNT(*) FILTER (WHERE ti.rsi_14 > 50) * 100.0 / NULLIF(COUNT(*), 0) AS pct
        FROM technical_indicators ti
        JOIN stocks s ON ti.stock_id = s.id
        WHERE s.market = 'IN' AND ti.date = (
            SELECT MAX(date) FROM technical_indicators WHERE stock_id = ti.stock_id
        )
        """
    )
    if pct_rsi and pct_rsi["pct"] is not None:
        components["pct_rsi_above_50"] = round(float(pct_rsi["pct"]), 1)

    sentiment = query_one(
        """
        SELECT AVG(sentiment_score) AS avg
        FROM news_sentiment
        WHERE date >= CURRENT_DATE - 3 AND sentiment_score IS NOT NULL
        """
    )
    if sentiment and sentiment["avg"] is not None:
        components["avg_sentiment"] = round(float(sentiment["avg"]), 2)

    return components


@router.get("/fear-greed")
def fear_greed_widget(history: int = 30):
    """
    Fear & Greed Index for India and US.

    Returns JSON optimized for widget display:
    - score: 0-100
    - label: Extreme Fear / Fear / Neutral / Greed / Extreme Greed
    - direction: up / down / flat
    - previous_score: prior day's score
    - components (India only): VIX, PCR, FII flow, % above SMA50, % RSI > 50, sentiment
    - history: last N days [{date, score}, ...]
    """
    india = _get_fg_data("IN", "india_fear_greed_index", history)
    india["components"] = _get_india_components()

    us = _get_fg_data("US", "us_fear_greed_index", history)

    return {
        "india": india,
        "us": us,
    }
