"""backtest/macro_cycle.py — growth/inflation business-cycle classifier for sector rotation.

macro_indicators.date is the indicator's PERIOD (quarter/month start-ish), not its publish
date — GDP/CPI prints are released weeks-to-months after the period they describe. Using
`date` directly as "known as of that date" would leak future macro data into a backtest
(a real look-ahead bug, not a nitpick). This module fixes that with a conservative
per-indicator release lag: a row only counts as "known" as of `date + lag_days`.

gdp_growth_yoy's `date` column is itself inconsistent in this DB — some rows look like
quarter-start, others quarter-end, across two different period-label conventions
("2025-Q4" vs "Q2 2025-26"). Rather than trying to parse/fix that ambiguity precisely,
the lags below are deliberately generous — biased toward "found out later than we might
have", never earlier, since an over-conservative lag just delays a phase call by a few
weeks while an under-conservative one silently invalidates a backtest with look-ahead bias.

Phase = classic growth/inflation quadrant. Phase -> favored-sector mapping is the textbook
(untested here) prior, not a data-fitted result — with only ~2 years of history (well under
one full business cycle), fitting our own sector returns per phase would just be noise.
Revisit once more history accumulates.

Inflation uses `wpi_inflation` (market='IN'), NOT `cpi_inflation_yoy` — that indicator name
exists in this DB but is tagged market='US' (40 rows), not India's. India's own CPI series
(`cpi_inflation`, market='IN') has only 1 row so far, unusable; `wpi_inflation` (market='IN',
16 rows, 2025-01→2026-04) is the only real India inflation history available today. This
also means the phase timeline can't start before ~2025 regardless of GDP history depth.
"""
from datetime import date, timedelta
from enum import Enum

from utils.db import get_conn

_RELEASE_LAG_DAYS = {
    "gdp_growth_yoy": 120,
    "wpi_inflation": 45,
}


class Phase(str, Enum):
    RECOVERY = "Recovery"        # growth up, inflation down
    OVERHEAT = "Overheat"        # growth up, inflation up
    STAGFLATION = "Stagflation"  # growth down, inflation up
    SLOWDOWN = "Slowdown"        # growth down, inflation down


PHASE_SECTORS = {
    Phase.RECOVERY: {"Financial Services", "Consumer Discretionary"},
    Phase.OVERHEAT: {"Commodities", "Energy", "Industrials"},
    Phase.STAGFLATION: {"Fast Moving Consumer Goods", "Healthcare", "Utilities"},
    Phase.SLOWDOWN: {"Information Technology", "Healthcare"},
}


def _load_indicator(indicator: str) -> list[tuple]:
    """[(period_date, value, known_as_of_date)] ascending by period_date."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT date, value FROM macro_indicators WHERE indicator=%s AND market='IN' "
                "AND value IS NOT NULL ORDER BY date", (indicator,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    lag = timedelta(days=_RELEASE_LAG_DAYS[indicator])
    return [(d, float(v), d + lag) for d, v in rows]


def build_phase_timeline() -> list[tuple[date, "Phase"]]:
    """[(known_as_of_date, phase)] ascending — phase is effective from known_as_of_date
    until superseded by the next entry. Built once from full history (not per-date
    queries) so phase_series() is cheap even over a multi-year date range.

    Known simplification: growth/inflation direction compares only the latest print
    vs. the immediately preceding one, not a trailing average — noisier than ideal
    (verified live: 19 "transitions" over ~16 months, more churn than a real business
    cycle). A 3-print trailing-average comparison would smooth this; left as a known
    gap rather than built now."""
    gdp = _load_indicator("gdp_growth_yoy")
    wpi = _load_indicator("wpi_inflation")

    events = []  # (known_as_of, kind, is_up)
    for i in range(1, len(gdp)):
        events.append((gdp[i][2], "gdp", gdp[i][1] > gdp[i - 1][1]))
    for i in range(1, len(wpi)):
        events.append((wpi[i][2], "wpi", wpi[i][1] > wpi[i - 1][1]))
    events.sort(key=lambda e: e[0])

    timeline: list[tuple[date, Phase]] = []
    growth_up = inflation_up = None
    for known_as_of, kind, is_up in events:
        if kind == "gdp":
            growth_up = is_up
        else:
            inflation_up = is_up
        if growth_up is None or inflation_up is None:
            continue
        if growth_up and not inflation_up:
            phase = Phase.RECOVERY
        elif growth_up and inflation_up:
            phase = Phase.OVERHEAT
        elif not growth_up and inflation_up:
            phase = Phase.STAGFLATION
        else:
            phase = Phase.SLOWDOWN
        timeline.append((known_as_of, phase))
    return timeline


def phase_series(dates: list[date]) -> dict:
    """{date: Phase|None} for each date in `dates` (e.g. a backtest's price panel
    index) — None where not enough macro history was known yet to classify."""
    timeline = build_phase_timeline()
    result = {}
    if not timeline:
        return {d: None for d in dates}
    idx = 0
    current_phase = None
    for d in sorted(dates):
        while idx < len(timeline) and timeline[idx][0] <= d:
            current_phase = timeline[idx][1]
            idx += 1
        result[d] = current_phase
    return result


def classify_phase(as_of: date) -> "Phase | None":
    """Single-date convenience wrapper around phase_series (e.g. for live recommendations)."""
    return phase_series([as_of])[as_of]
