"""Data freshness + refresh control.

Everything reads from data_refresh_log (one row per source = its latest run).
Manual "Refresh Now" launches the corresponding Dagster asset via GraphQL.
"""
from datetime import datetime, timedelta

from fastapi import APIRouter
from pydantic import BaseModel

from db import query_all, query_one
import dagster_client

router = APIRouter(prefix="/api/refresh", tags=["refresh"])

# source -> what it provides + the Dagster asset that refreshes it (None = no asset wired)
SOURCE_META: dict[str, dict] = {
    "kite_ohlcv": {"provides": "Daily OHLCV prices (watchlist)", "asset": "nse_raw_prices"},
    "kite_quotes": {"provides": "Live quotes (watchlist)", "asset": "nse_raw_prices"},
    "tech_indicators": {"provides": "RSI, SMA, EMA, MACD, Bollinger Bands", "asset": "nse_technical_indicators"},
    "signals": {"provides": "BUY/SELL/WATCH signal report", "asset": "nse_signals"},
    "fii_dii": {"provides": "FII / DII net flows", "asset": "nse_fii_dii_flows"},
    "nse_actions": {"provides": "Corporate actions + earnings calendar", "asset": "nse_corporate_actions"},
    "news_sentiment": {"provides": "News headlines + FinBERT sentiment", "asset": "nse_news_sentiment"},
    "fno_data": {"provides": "India VIX, Put/Call ratio, FII OI", "asset": "nse_fno_data"},
    "block_deals": {"provides": "NSE block deals", "asset": "nse_block_deals"},
    "bulk_deals": {"provides": "NSE / BSE bulk deals", "asset": "bse_bulk_deals"},
    "shareholding_pattern": {"provides": "Quarterly shareholding pattern", "asset": "nse_shareholding_pattern"},
    "screener": {"provides": "Fundamentals (P/E, ROE, ROCE, …)", "asset": "nse_fundamentals"},
    "fundamentals_full": {"provides": "Full fundamentals refresh", "asset": "nse_fundamentals"},
    "rbi_macro": {"provides": "RBI policy rates (DBIE homepage)", "asset": "nse_macro_indicators"},
    "mospi_macro": {"provides": "GDP + WPI (MoSPI MCP)", "asset": "nse_macro_indicators"},
    "rbi_dbie": {"provides": "Forex reserves + bank credit (RBI DBIE)", "asset": "nse_macro_indicators"},
    "insider_trades": {"provides": "Insider (SEBI PIT) + bulk deals", "asset": "nse_insider_trades"},
    "google_trends": {"provides": "Google search interest (proxy)", "asset": "nse_google_trends"},
    "model_refresh": {"provides": "Stock scores + baselines (monthly model)", "asset": "nse_model_refresh"},
    "us_prices": {"provides": "US OHLCV prices", "asset": "us_raw_prices"},
    "sec_form4": {"provides": "US insider trades (SEC Form 4)", "asset": "us_insider_trades"},
    "fred_macro": {"provides": "US macro (FRED: rates, CPI, GDP, …)", "asset": "us_macro"},
    "sector_indices": {"provides": "NSE sector indices", "asset": None},
    "whatsapp": {"provides": "WhatsApp expert chat signals", "asset": None},
}

# Max age (days) before a source of a given tier is considered stale. event-driven = no SLA.
TIER_MAX_AGE_DAYS = {"daily": 2, "weekly": 8, "monthly": 35, "quarterly": 100}

# Which sources back each page's data (for the "Last updated" badge).
PAGE_SOURCES = {
    "dashboard": ["signals", "tech_indicators"],
    "stock": ["kite_ohlcv", "tech_indicators"],
    "macro": ["rbi_dbie", "mospi_macro", "rbi_macro", "fred_macro"],
    "watchlist": ["signals", "tech_indicators"],
    "opportunities": ["news_sentiment", "insider_trades"],
}


def _iso(dt):
    return dt.isoformat() if isinstance(dt, datetime) else dt


def _is_stale(tier: str, completed_at, status: str) -> bool:
    max_age = TIER_MAX_AGE_DAYS.get(tier)
    if max_age is None:
        return False
    if status == "never_run" or completed_at is None:
        return True
    age = datetime.now() - completed_at
    return age > timedelta(days=max_age)


@router.get("/last")
def last_updated(sources: str = "", page: str = ""):
    """Most-recent run among the given sources (or a page's sources). For the badge."""
    names = [s for s in sources.split(",") if s] or PAGE_SOURCES.get(page, [])
    if not names:
        return {"source": None, "completed_at": None, "status": None}
    rows = query_all(
        "SELECT source, status, completed_at, rows_upserted FROM data_refresh_log "
        "WHERE source = ANY(%s)",
        (names,),
    )
    dated = [r for r in rows if r["completed_at"] is not None]
    if not dated:
        return {"source": names[0], "completed_at": None, "status": "never_run"}
    latest = max(dated, key=lambda r: r["completed_at"])
    return {
        "source": latest["source"],
        "completed_at": _iso(latest["completed_at"]),
        "status": latest["status"],
        "rows_upserted": latest["rows_upserted"],
    }


@router.get("/sources")
def sources():
    rows = query_all(
        "SELECT source, tier, status, started_at, completed_at, rows_upserted, error_message "
        "FROM data_refresh_log ORDER BY source"
    )
    out = []
    for r in rows:
        meta = SOURCE_META.get(r["source"], {})
        out.append({
            "source": r["source"],
            "provides": meta.get("provides", "—"),
            "frequency": r["tier"],
            "status": r["status"],
            "completed_at": _iso(r["completed_at"]),
            "rows_upserted": r["rows_upserted"],
            "stale": _is_stale(r["tier"], r["completed_at"], r["status"]),
            "triggerable": meta.get("asset") is not None,
        })
    # sort: failed first, then stale, then by source
    rank = {"error": 0, "running": 1, "never_run": 3}
    out.sort(key=lambda r: (rank.get(r["status"], 2), not r["stale"], r["source"]))
    return {"sources": out, "dagster_healthy": dagster_client.healthy()}


@router.get("/status")
def status():
    rows = query_all(
        "SELECT source, tier, status, started_at, completed_at, rows_upserted, error_message "
        "FROM data_refresh_log"
    )
    week_ago = datetime.now() - timedelta(days=7)
    failures = [
        {"source": r["source"], "completed_at": _iso(r["completed_at"]),
         "error_message": r["error_message"], "tier": r["tier"]}
        for r in rows
        if r["status"] == "error" and (r["completed_at"] is None or r["completed_at"] >= week_ago)
    ]
    stale = [
        {"source": r["source"], "tier": r["tier"], "status": r["status"],
         "completed_at": _iso(r["completed_at"]),
         "max_age_days": TIER_MAX_AGE_DAYS.get(r["tier"])}
        for r in rows
        if _is_stale(r["tier"], r["completed_at"], r["status"])
    ]
    history = sorted(
        ({
            "source": r["source"], "tier": r["tier"], "status": r["status"],
            "started_at": _iso(r["started_at"]), "completed_at": _iso(r["completed_at"]),
            "rows_upserted": r["rows_upserted"], "error_message": r["error_message"],
        } for r in rows),
        key=lambda r: (r["completed_at"] is None, r["completed_at"] or ""),
        reverse=True,
    )
    return {
        "failures": failures,
        "stale": sorted(stale, key=lambda s: s["source"]),
        "history": history,  # latest run per source (data_refresh_log keeps one row/source)
        "dagster_healthy": dagster_client.healthy(),
    }


class TriggerReq(BaseModel):
    source: str


@router.post("/trigger")
def trigger(req: TriggerReq):
    meta = SOURCE_META.get(req.source)
    if not meta:
        return {"ok": False, "error": f"Unknown source '{req.source}'"}
    asset = meta.get("asset")
    if not asset:
        return {"ok": False, "error": f"'{req.source}' has no Dagster asset wired to trigger."}
    result = dagster_client.launch_asset(asset)
    result["source"] = req.source
    result["asset"] = asset
    return result


@router.get("/run-status")
def get_run_status(run_id: str):
    return dagster_client.run_status(run_id)
