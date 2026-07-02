"""Data freshness + refresh control.

Everything reads from data_refresh_log (one row per source = its latest run).
Manual "Refresh Now" launches the corresponding Dagster asset via GraphQL.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from pydantic import BaseModel

from db import query_all, query_one, get_cursor
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
    "quarterly_financials": {"provides": "Quarterly results, financials & concalls (Screener)", "asset": "nse_quarterly_financials"},
    "fear_greed": {"provides": "India + US Fear & Greed Index", "asset": "india_fear_greed"},
    "model_refresh": {"provides": "Stock scores + baselines (monthly model)", "asset": "nse_model_refresh"},
    "us_prices": {"provides": "US OHLCV prices", "asset": "us_raw_prices"},
    "sec_form4": {"provides": "US insider trades (SEC Form 4)", "asset": "us_insider_trades"},
    "fred_macro": {"provides": "US macro (FRED: rates, CPI, GDP, …)", "asset": "us_macro"},
    "sec_13f": {"provides": "US 13F institutional holdings", "asset": "us_13f_holdings"},
    "kite_token": {"provides": "Kite access token (daily refresh)", "asset": "kite_token_refreshed"},
    "sast_disclosures": {"provides": "SAST substantial-acquisition disclosures", "asset": "nse_sast_disclosures"},
    "pledging_alerts": {"provides": "Promoter share-pledging alerts", "asset": "nse_pledging_alerts"},
    "analyst_targets": {"provides": "Analyst price targets", "asset": "nse_analyst_targets"},
    "mf_stock_holdings": {"provides": "MF / DII stock holdings (proxy)", "asset": "nse_mf_holdings"},
    "sector_indices": {"provides": "NSE sector indices", "asset": None},
    "whatsapp": {"provides": "WhatsApp expert chat signals", "asset": None},
    "congress_trades": {"provides": "US Congress trades (source blocked)", "asset": None},
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


# ---------------------------------------------------------------------------
# Unified refresh control (/refresh page): job groups + real status + schedules
# ---------------------------------------------------------------------------

# A run stuck in 'running' longer than this (with no completion) is treated as
# stalled — Dagster process died without the refresh_log context manager closing
# the row. This is the root cause of the phantom "failures" the old UI showed.
STALLED_AFTER = timedelta(hours=3)

IST = "Asia/Kolkata"
EST = "America/New_York"

# Ordered job groups. Each job: (source, label, [cron], [tz], [sched_label]).
# Cron/tz/sched_label fall back to the group's when omitted. cron drives next-run.
JOB_GROUPS = [
    {
        "id": "india_daily", "title": "India Daily", "flag": "🇮🇳", "region": "India",
        "cron": "0 16 * * 1-5", "tz": IST, "sched_label": "Mon–Fri 16:00 IST",
        "jobs": [
            ("kite_token", "Kite Token", "0 8 * * *", IST, "Daily 08:00 IST"),
            ("kite_ohlcv", "OHLCV Prices", None, None, None),
            ("tech_indicators", "Technicals", None, None, None),
            ("fii_dii", "FII / DII", "30 16 * * 1-5", IST, "Mon–Fri 16:30 IST"),
            ("fno_data", "F&O Data", "45 16 * * 1-5", IST, "Mon–Fri 16:45 IST"),
            ("block_deals", "Block Deals", "30 16 * * 1-5", IST, "Mon–Fri 16:30 IST"),
            ("bulk_deals", "Bulk Deals", "30 16 * * 1-5", IST, "Mon–Fri 16:30 IST"),
            ("nse_actions", "Corp Actions", None, None, None),
            ("news_sentiment", "News Sentiment", None, None, None),
            ("fear_greed", "Fear & Greed", None, None, None),
            ("signals", "Signals", None, None, None),
        ],
    },
    {
        "id": "india_weekly", "title": "India Weekly", "flag": "🇮🇳", "region": "India",
        "cron": "30 7 * * 0", "tz": IST, "sched_label": "Sun 07:30 IST",
        "jobs": [
            ("screener", "Fundamentals", None, None, None),
            ("quarterly_financials", "Quarterly Results", None, None, None),
            ("insider_trades", "Insider Trades", None, None, None),
            ("shareholding_pattern", "Shareholding", None, None, None),
            ("sast_disclosures", "SAST Disclosures", None, None, None),
            ("pledging_alerts", "Pledging Alerts", None, None, None),
            ("analyst_targets", "Analyst Targets", None, None, None),
            ("google_trends", "Google Trends", None, None, None),
            ("rbi_dbie", "RBI DBIE Macro", None, None, None),
            ("mospi_macro", "MoSPI Macro", None, None, None),
            ("rbi_macro", "RBI Rates", None, None, None),
        ],
    },
    {
        "id": "india_monthly", "title": "India Monthly", "flag": "🇮🇳", "region": "India",
        "cron": "0 2 1 * *", "tz": IST, "sched_label": "1st of month 02:00 IST",
        "jobs": [
            ("model_refresh", "Model Refresh", None, None, None),
            ("mf_stock_holdings", "MF Holdings", None, None, None),
        ],
    },
    {
        "id": "us_daily", "title": "US Daily", "flag": "🇺🇸", "region": "US",
        "cron": "30 16 * * 1-5", "tz": EST, "sched_label": "Mon–Fri 16:30 EST",
        "jobs": [
            ("us_prices", "US Prices", None, None, None),
            ("sec_form4", "US Insider (Form 4)", None, None, None),
        ],
    },
    {
        "id": "us_weekly", "title": "US Weekly", "flag": "🇺🇸", "region": "US",
        "cron": "0 7 * * 0", "tz": EST, "sched_label": "Sun 07:00 EST",
        "jobs": [
            ("fred_macro", "US Macro (FRED)", None, None, None),
            ("sec_13f", "13F Holdings", None, None, None),
        ],
    },
]

# Every source that belongs to a group (so we can list the leftovers under "Other").
_GROUPED_SOURCES = {j[0] for g in JOB_GROUPS for j in g["jobs"]}


def _parse_dow(dow: str):
    """cron day-of-week (0/7=Sun) -> set of ints {0=Sun..6=Sat}, or None for any."""
    if dow == "*":
        return None
    if "-" in dow:
        a, b = (int(x) for x in dow.split("-"))
        return {d % 7 for d in range(a, b + 1)}
    return {int(dow) % 7}


def _next_run(cron: str, tz: str):
    """Next fire time for a simple 'm h dom mon dow' cron (single m/h). ISO or None."""
    try:
        m_s, h_s, dom_s, _mon_s, dow_s = cron.split()
        minute, hour = int(m_s), int(h_s)
    except Exception:  # noqa: BLE001
        return None
    dow_set = _parse_dow(dow_s)
    dom = None if dom_s == "*" else int(dom_s)
    now = datetime.now(ZoneInfo(tz))
    base = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    for i in range(0, 400):
        c = base + timedelta(days=i)
        if c <= now:
            continue
        if dow_set is not None and (c.isoweekday() % 7) not in dow_set:
            continue
        if dom is not None and c.day != dom:
            continue
        return c.isoformat()
    return None


def _effective_status(row: dict) -> str:
    """Collapse the raw data_refresh_log status into what the UI should show.

    Turns a run stuck in 'running' with no recent activity into 'stalled' so it
    reads as a real problem (this is the phantom-failure fix)."""
    st = row.get("status")
    if st == "running":
        anchor = row.get("started_at") or row.get("completed_at")
        # a 'running' row that already has a completed_at, or started long ago,
        # is an orphaned run — the process died without closing the log row.
        if row.get("completed_at") is not None or (
            anchor is not None and datetime.now() - anchor > STALLED_AFTER
        ):
            return "stalled"
    return st or "never_run"


# statuses that count as "needs attention" for health + Retry-Failed.
_UNHEALTHY = {"error", "stalled", "never_run", "retrying", "partial"}


def _job_payload(source: str, label: str, cron: str, tz: str, sched_label: str,
                 by_source: dict) -> dict:
    row = by_source.get(source) or {}
    eff = _effective_status(row) if row else "never_run"
    started, completed = row.get("started_at"), row.get("completed_at")
    duration = None
    if started and completed and completed >= started:
        duration = round((completed - started).total_seconds())
    meta = SOURCE_META.get(source, {})
    return {
        "source": source,
        "label": label,
        "provides": meta.get("provides", "—"),
        "status": eff,
        "raw_status": row.get("status"),
        "started_at": _iso(started),
        "completed_at": _iso(completed),
        "duration_secs": duration,
        "rows_upserted": row.get("rows_upserted"),
        "error_message": row.get("error_message"),
        "coverage_pct": float(row["coverage_pct"]) if row.get("coverage_pct") is not None else None,
        "retry_count": row.get("retry_count") or 0,
        "tier": row.get("tier"),
        "schedule": sched_label,
        "next_run": _next_run(cron, tz),
        "triggerable": meta.get("asset") is not None,
    }


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


# data_refresh_log source -> data_quality_log.table_name (for gap counts per source)
SOURCE_TABLE = {
    "kite_ohlcv": "daily_prices", "tech_indicators": "technical_indicators",
    "screener": "fundamentals", "fundamentals_full": "fundamentals",
    "news_sentiment": "news_sentiment", "shareholding_pattern": "shareholding_pattern",
    "signals": "stock_scores",
}


@router.get("/sources")
def sources():
    rows = query_all(
        "SELECT source, tier, status, started_at, completed_at, rows_upserted, error_message, "
        "expected_rows, actual_rows, coverage_pct, retry_count "
        "FROM data_refresh_log ORDER BY source"
    )
    gap_by_table = {r["table_name"]: r["n"] for r in query_all(
        "SELECT table_name, COUNT(*) AS n FROM data_quality_log WHERE resolved_at IS NULL GROUP BY table_name")}
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
            "coverage_pct": float(r["coverage_pct"]) if r["coverage_pct"] is not None else None,
            "retry_count": r["retry_count"],
            "gaps": gap_by_table.get(SOURCE_TABLE.get(r["source"]), 0),
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


def _launch_sources(source_names: list[str]) -> list[dict]:
    """Launch each source's asset once (dedupe shared assets, e.g. the 3 macro sources)."""
    launched, seen = [], set()
    for src in source_names:
        asset = (SOURCE_META.get(src) or {}).get("asset")
        if not asset or asset in seen:
            continue
        seen.add(asset)
        res = dagster_client.launch_asset(asset)
        launched.append({"source": src, "asset": asset, **res})
    return launched


@router.post("/trigger-all")
def trigger_all():
    """Refresh every triggerable source (assets deduped) — runs in parallel via Dagster."""
    triggerable = [s for s, m in SOURCE_META.items() if m.get("asset")]
    launched = _launch_sources(triggerable)
    ok = sum(1 for r in launched if r.get("ok"))
    return {"launched": launched, "count": len(launched), "ok": ok}


@router.post("/trigger-region")
def trigger_region(region: str):
    """Refresh only one market's jobs — region = 'India' or 'US'."""
    sources = [j[0] for g in JOB_GROUPS if g["region"].lower() == region.lower()
               for j in g["jobs"]]
    launched = _launch_sources(sources)
    ok = sum(1 for r in launched if r.get("ok"))
    return {"region": region, "launched": launched, "count": len(launched), "ok": ok}


@router.post("/trigger-failed")
def trigger_failed():
    """Refresh only sources that need attention: failed, stalled, never-run,
    retrying, or partial (evaluated the same way the /control page shows them)."""
    rows = query_all(
        "SELECT source, status, started_at, completed_at FROM data_refresh_log"
    )
    names = [
        r["source"] for r in rows
        if _effective_status(r) in _UNHEALTHY
        and (SOURCE_META.get(r["source"]) or {}).get("asset")
    ]
    launched = _launch_sources(names)
    ok = sum(1 for r in launched if r.get("ok"))
    return {"launched": launched, "count": len(launched), "ok": ok}


@router.post("/trigger-full")
def trigger_full():
    """Force Full Refresh: clear all open data-quality gaps, then re-run every
    triggerable source so the whole pipeline recomputes from scratch."""
    cleared = 0
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE data_quality_log SET resolved_at = now() "
            "WHERE resolved_at IS NULL RETURNING id"
        )
        cleared = cur.rowcount
        # reset retry counters so the watchdog/quality sensors start clean
        cur.execute("UPDATE data_refresh_log SET retry_count = 0")
    triggerable = [s for s, m in SOURCE_META.items() if m.get("asset")]
    launched = _launch_sources(triggerable)
    ok = sum(1 for r in launched if r.get("ok"))
    return {"gaps_cleared": cleared, "launched": launched, "count": len(launched), "ok": ok}


@router.get("/run-status")
def get_run_status(run_id: str):
    return dagster_client.run_status(run_id)


def _all_rows_by_source() -> dict:
    rows = query_all(
        "SELECT source, tier, status, started_at, completed_at, rows_upserted, "
        "error_message, coverage_pct, retry_count FROM data_refresh_log"
    )
    return {r["source"]: r for r in rows}


def _derive_health(jobs: list[dict]) -> dict:
    """Single source of truth: roll up per-source data_refresh_log statuses."""
    failed = [j["source"] for j in jobs if j["status"] in ("error", "stalled")]
    attention = [j["source"] for j in jobs if j["status"] in ("retrying", "partial", "never_run")]
    stale = [j["source"] for j in jobs
             if _is_stale(j.get("tier"), _parse_iso(j["completed_at"]), j["status"])]
    if failed:
        level, color = "failed", "red"
    elif stale or attention:
        level, color = "stale", "yellow"
    else:
        level, color = "healthy", "green"
    return {
        "level": level, "color": color,
        "failed": failed, "attention": attention, "stale": stale,
        "counts": {
            "total": len(jobs),
            "success": sum(1 for j in jobs if j["status"] == "success"),
            "failed": len(failed), "attention": len(attention), "stale": len(stale),
        },
    }


def _parse_iso(s):
    return datetime.fromisoformat(s) if s else None


@router.get("/control")
def control():
    """Everything the unified /refresh page needs, from data_refresh_log only.

    Groups jobs by India/US × cadence, with real status, duration, rows, next
    scheduled run, and a derived overall health — one source of truth."""
    by_source = _all_rows_by_source()
    groups, all_jobs = [], []
    for g in JOB_GROUPS:
        jobs = []
        for source, label, cron, tz, sched in g["jobs"]:
            jobs.append(_job_payload(
                source, label,
                cron or g["cron"], tz or g["tz"], sched or g["sched_label"],
                by_source,
            ))
        all_jobs.extend(jobs)
        groups.append({
            "id": g["id"], "title": g["title"], "flag": g["flag"], "region": g["region"],
            "schedule": g["sched_label"], "next_run": _next_run(g["cron"], g["tz"]),
            "jobs": jobs,
        })

    # anything in data_refresh_log we didn't place in a group — surface it honestly
    other = []
    for source, row in sorted(by_source.items()):
        if source in _GROUPED_SOURCES:
            continue
        other.append(_job_payload(source, source, "", "", "no schedule", by_source))
    if other:
        all_jobs.extend(other)
        groups.append({
            "id": "other", "title": "Other / Untracked", "flag": "⚙️", "region": "—",
            "schedule": "—", "next_run": None, "jobs": other,
        })

    # "last full refresh" = when the India daily pipeline last finished (signals is
    # the terminal asset, downstream of every daily collector).
    sig = by_source.get("signals") or {}
    last_full = _iso(sig.get("completed_at")) if sig.get("status") == "success" else None

    return {
        "groups": groups,
        "health": _derive_health(all_jobs),
        "last_full_refresh": last_full,
        "dagster_healthy": dagster_client.healthy(),
        "server_time": datetime.now().isoformat(),
    }


@router.get("/health")
def refresh_health():
    """Compact health for the global header banner — same source of truth as
    /control, so every page agrees (fixes the 'one page says failed' mismatch)."""
    by_source = _all_rows_by_source()
    jobs = []
    for g in JOB_GROUPS:
        for source, label, cron, tz, sched in g["jobs"]:
            jobs.append(_job_payload(source, label, cron or g["cron"],
                                     tz or g["tz"], sched or g["sched_label"], by_source))
    h = _derive_health(jobs)
    return {"level": h["level"], "color": h["color"], "counts": h["counts"],
            "dagster_healthy": dagster_client.healthy()}


@router.post("/trigger-audit")
def trigger_audit():
    """Run the data-quality audit assets (gap detection + completeness scoring)."""
    launched = []
    for asset in ("nse_daily_audit", "nse_weekly_audit"):
        res = dagster_client.launch_asset(asset)
        launched.append({"asset": asset, **res})
    ok = sum(1 for r in launched if r.get("ok"))
    return {"launched": launched, "count": len(launched), "ok": ok}
