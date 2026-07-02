"""Macro snapshot — RBI rates, forex reserves, FII/DII flows, GDP, WPI."""
from fastapi import APIRouter

from db import query_all, query_one

router = APIRouter(prefix="/api/macro", tags=["macro"])

# Grouping of macro_indicators.indicator -> display section
_RATES = ["repo_rate", "reverse_repo_rate", "crr", "slr", "sdf_rate", "wacr", "usd_inr"]
_GROWTH = ["gdp_growth_yoy", "wpi_inflation", "cpi_inflation"]
_FOREX = ["forex_reserves_total", "forex_reserves_fca", "forex_reserves_gold",
          "forex_reserves_sdr", "forex_reserves_imf"]
_CREDIT = ["bank_credit_growth_yoy", "non_food_credit_growth_yoy",
           "aggregate_deposits_growth_yoy", "credit_deposit_ratio"]


def _latest(indicators: list[str], market: str = "IN") -> list[dict]:
    """Latest value per indicator (DISTINCT ON date desc) for a given market."""
    return query_all(
        """
        SELECT DISTINCT ON (indicator) indicator, value, unit, period, date, source
        FROM macro_indicators
        WHERE market = %s AND indicator = ANY(%s)
        ORDER BY indicator, date DESC
        """,
        (market, indicators),
    )


# US macro (FRED) — kept strictly separate from India metrics
_US_RATES = ["fed_funds_rate"]
_US_GROWTH = ["gdp_growth_yoy", "cpi_inflation_yoy", "unemployment_rate"]


def _series(indicator: str, limit: int = 26) -> list[dict]:
    rows = query_all(
        "SELECT date, value FROM macro_indicators "
        "WHERE market = 'IN' AND indicator = %s ORDER BY date DESC LIMIT %s",
        (indicator, limit),
    )
    return list(reversed(rows))


def _us_series(indicator: str, limit: int = 13) -> list[dict]:
    rows = query_all(
        "SELECT date, value FROM macro_indicators "
        "WHERE market = 'US' AND indicator = %s ORDER BY date DESC LIMIT %s",
        (indicator, limit),
    )
    return list(reversed(rows))


@router.get("")
def snapshot():
    fii_dii = query_one(
        "SELECT date, fii_buy, fii_sell, fii_net, dii_buy, dii_sell, dii_net "
        "FROM fii_dii_flows ORDER BY date DESC LIMIT 1"
    )
    fno = query_one(
        "SELECT date, india_vix, index_pcr, total_pcr, max_pain "
        "FROM fno_data ORDER BY date DESC LIMIT 1"
    )
    return {
        "rates": _latest(_RATES),
        "growth": _latest(_GROWTH),
        "forex": _latest(_FOREX),
        "credit": _latest(_CREDIT),
        "fii_dii": fii_dii,
        "fno": fno,
        "trends": {
            "forex_reserves_total": _series("forex_reserves_total"),
            "gdp_growth_yoy": _series("gdp_growth_yoy", 8),
            "wpi_inflation": _series("wpi_inflation", 13),
        },
        # US macro (FRED) — separate section, never mixed with India metrics
        "us": {
            "rates": _latest(_US_RATES, "US"),
            "growth": _latest(_US_GROWTH, "US"),
            "trends": {
                "gdp_growth_yoy": _us_series("gdp_growth_yoy", 8),
                "cpi_inflation_yoy": _us_series("cpi_inflation_yoy", 13),
                "unemployment_rate": _us_series("unemployment_rate", 13),
            },
        },
    }


@router.get("/fii-dii")
def fii_dii_history(limit: int = 30):
    rows = query_all(
        "SELECT date, fii_net, dii_net FROM fii_dii_flows ORDER BY date DESC LIMIT %s",
        (limit,),
    )
    return list(reversed(rows))


def _streak(nets: list[float]) -> dict:
    """Consecutive same-direction run ending at the latest day (nets newest-first)."""
    if not nets or nets[0] is None or nets[0] == 0:
        return {"direction": "flat", "days": 0}
    direction = "buying" if nets[0] > 0 else "selling"
    days = 0
    for v in nets:
        if v is None or v == 0:
            break
        if (v > 0) == (nets[0] > 0):
            days += 1
        else:
            break
    return {"direction": direction, "days": days}


@router.get("/fii-dii-trend")
def fii_dii_trend(limit: int = 30):
    """30-day FII/DII net flows with 5d/10d moving averages + summary stats & streaks.

    Powers the Macro FII/DII day-over-day chart: green/red daily bars, MA overlays,
    cumulative 5-day flow, consecutive buying/selling streaks, today-vs-yesterday.
    """
    rows = query_all(
        "SELECT date, fii_net, dii_net FROM fii_dii_flows ORDER BY date DESC LIMIT %s",
        (limit,),
    )
    rows = list(reversed(rows))  # chronological (oldest -> newest)
    fii = [float(r["fii_net"]) if r["fii_net"] is not None else None for r in rows]
    dii = [float(r["dii_net"]) if r["dii_net"] is not None else None for r in rows]

    def ma(vals, i, w):
        window = [v for v in vals[max(0, i - w + 1): i + 1] if v is not None]
        return round(sum(window) / len(window), 1) if window else None

    series = []
    for i, r in enumerate(rows):
        series.append({
            "date": r["date"].isoformat() if r["date"] else None,
            "fii_net": fii[i], "dii_net": dii[i],
            "fii_ma5": ma(fii, i, 5), "fii_ma10": ma(fii, i, 10),
            "dii_ma5": ma(dii, i, 5), "dii_ma10": ma(dii, i, 10),
        })

    fii_rev = list(reversed(fii))  # newest-first for streaks / today-vs-prev
    dii_rev = list(reversed(dii))

    def cum(vals, n):
        return round(sum(v for v in vals[:n] if v is not None), 1)

    def latest_two(vals):
        cur = vals[0] if vals else None
        prev = vals[1] if len(vals) > 1 else None
        chg = round(cur - prev, 1) if (cur is not None and prev is not None) else None
        return cur, prev, chg

    fii_today, fii_prev, fii_chg = latest_two(fii_rev)
    dii_today, dii_prev, dii_chg = latest_two(dii_rev)

    return {
        "series": series,
        "summary": {
            "fii_5d_cum": cum(fii_rev, 5), "dii_5d_cum": cum(dii_rev, 5),
            "fii_10d_cum": cum(fii_rev, 10), "dii_10d_cum": cum(dii_rev, 10),
            "fii_streak": _streak(fii_rev), "dii_streak": _streak(dii_rev),
            "fii_today": fii_today, "fii_prev": fii_prev, "fii_change": fii_chg,
            "dii_today": dii_today, "dii_prev": dii_prev, "dii_change": dii_chg,
            "latest_date": series[-1]["date"] if series else None,
        },
    }


def _fg_rating(score):
    if score is None:
        return None
    return ("Extreme Fear" if score < 25 else "Fear" if score < 45 else
            "Neutral" if score < 55 else "Greed" if score < 75 else "Extreme Greed")


@router.get("/fear-greed")
def fear_greed(history: int = 30):
    """India + US Fear & Greed: latest value, rating, and recent history for the chart."""
    out = {}
    for key, market, indicator in (("india", "IN", "india_fear_greed_index"),
                                   ("us", "US", "us_fear_greed_index")):
        latest = query_one(
            "SELECT date, value FROM macro_indicators "
            "WHERE market=%s AND indicator=%s ORDER BY date DESC LIMIT 1",
            (market, indicator),
        )
        rows = query_all(
            "SELECT date, value FROM macro_indicators "
            "WHERE market=%s AND indicator=%s ORDER BY date DESC LIMIT %s",
            (market, indicator, history),
        )
        score = float(latest["value"]) if latest and latest["value"] is not None else None
        out[key] = {
            "score": score,
            "rating": _fg_rating(score),
            "date": latest["date"] if latest else None,
            "history": list(reversed(rows)),
        }
    return out
