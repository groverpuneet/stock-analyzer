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


def _latest(indicators: list[str]) -> list[dict]:
    """Latest value per indicator (DISTINCT ON date desc)."""
    return query_all(
        """
        SELECT DISTINCT ON (indicator) indicator, value, unit, period, date, source
        FROM macro_indicators
        WHERE market = 'IN' AND indicator = ANY(%s)
        ORDER BY indicator, date DESC
        """,
        (indicators,),
    )


def _series(indicator: str, limit: int = 26) -> list[dict]:
    rows = query_all(
        "SELECT date, value FROM macro_indicators "
        "WHERE market = 'IN' AND indicator = %s ORDER BY date DESC LIMIT %s",
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
    }


@router.get("/fii-dii")
def fii_dii_history(limit: int = 30):
    rows = query_all(
        "SELECT date, fii_net, dii_net FROM fii_dii_flows ORDER BY date DESC LIMIT %s",
        (limit,),
    )
    return list(reversed(rows))


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
