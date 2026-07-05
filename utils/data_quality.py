"""
utils/data_quality.py — the data-quality framework.

Gap detection per domain, per-stock completeness scoring, and a gap ledger
(data_quality_log). Used by:
  - the enhanced refresh_log (utils/db.py) to record coverage/status,
  - the post_run_audit Dagster asset (runs after nse_daily/weekly jobs),
  - the data_quality_sensor (drains unresolved gaps every 30 min),
  - the web API (completeness scores + gap counts on the dashboard).

A "gap" is missing or stale data for a stock in some table. Each open gap is one
data_quality_log row (resolved_at NULL); it's resolved when the data later appears.

Completeness score (0-100), weighted so news (availability-limited for small caps)
doesn't dominate:
  price 20 · indicators 20 · signals 20 · fundamentals 15 · shareholding 15 · news 10
"""
import os
import json
from datetime import datetime, date

from utils.db import get_conn

WATCHLIST = "Default"

COMPLETENESS_WEIGHTS = {
    "price": 20, "indicators": 20, "signals": 20,
    "fundamentals": 15, "shareholding": 15, "news": 10,
}

# domain -> the gap detectors that a job in that domain is responsible for
DOMAIN_DETECTORS = {
    "nse_daily": ["ohlcv", "indicators", "signals", "news"],
    "nse_weekly": ["fundamentals", "shareholding"],
}


# ── watchlist + market helpers ────────────────────────────────────────────────

def _watchlist_ids(cur) -> list[int]:
    cur.execute(
        "SELECT s.id FROM watchlist w JOIN stocks s ON w.stock_id = s.id "
        "WHERE w.name = %s AND s.exchange = 'NSE'", (WATCHLIST,))
    return [r[0] for r in cur.fetchall()]


def _cohort_latest_date(cur, ids: list[int]):
    """Latest trading day within this cohort of stocks (avoids cross-market skew —
    NSE closes a day 'behind' US, so never compare NSE stocks to the global max)."""
    if not ids:
        return None
    cur.execute("SELECT MAX(date) FROM daily_prices WHERE stock_id = ANY(%s)", (ids,))
    return cur.fetchone()[0]


# ── gap ledger ────────────────────────────────────────────────────────────────

def log_gap(cur, stock_id, table_name: str, gap_type: str, detail: str = None):
    """Upsert an OPEN gap (no ON CONFLICT — works for NULL stock_id global gaps too)."""
    cur.execute(
        "UPDATE data_quality_log SET gap_detail=%s, detected_at=now() "
        "WHERE table_name=%s AND gap_type=%s AND resolved_at IS NULL "
        "AND stock_id IS NOT DISTINCT FROM %s",
        (detail, table_name, gap_type, stock_id))
    if cur.rowcount == 0:
        cur.execute(
            "INSERT INTO data_quality_log (stock_id, table_name, gap_type, gap_detail) "
            "VALUES (%s,%s,%s,%s)", (stock_id, table_name, gap_type, detail))


def resolve_gaps(cur, table_name: str, gap_type: str, present_ids: set[int]):
    """Mark resolved any open gaps of this type whose stock now HAS the data."""
    cur.execute(
        "SELECT id, stock_id FROM data_quality_log "
        "WHERE table_name=%s AND gap_type=%s AND resolved_at IS NULL",
        (table_name, gap_type))
    for gid, sid in cur.fetchall():
        if sid in present_ids:
            cur.execute("UPDATE data_quality_log SET resolved_at=now() WHERE id=%s", (gid,))


# ── per-domain gap detectors (return list of missing stock_ids, log gaps) ──────

def detect_ohlcv(cur) -> list[int]:
    """Watchlist stocks whose latest OHLCV is behind the cohort's latest trading day."""
    ids = _watchlist_ids(cur)
    latest = _cohort_latest_date(cur, ids)
    missing = []
    for sid in ids:
        cur.execute("SELECT MAX(date) FROM daily_prices WHERE stock_id=%s", (sid,))
        d = cur.fetchone()[0]
        if d is None or (latest and d < latest):
            log_gap(cur, sid, "daily_prices", "missing_ohlcv",
                    f"latest={d}, market_latest={latest}")
            missing.append(sid)
    resolve_gaps(cur, "daily_prices", "missing_ohlcv", set(ids) - set(missing))
    return missing


def detect_indicators(cur) -> list[int]:
    """Stocks with price data but no RSI/MACD on their latest price date."""
    ids = _watchlist_ids(cur)
    missing = []
    for sid in ids:
        cur.execute("""
            SELECT NOT EXISTS (
              SELECT 1 FROM technical_indicators ti
              WHERE ti.stock_id=%s AND ti.rsi_14 IS NOT NULL AND ti.macd IS NOT NULL
              AND ti.date=(SELECT MAX(date) FROM daily_prices dp WHERE dp.stock_id=%s))
            AND EXISTS (SELECT 1 FROM daily_prices dp WHERE dp.stock_id=%s)
        """, (sid, sid, sid))
        if cur.fetchone()[0]:
            log_gap(cur, sid, "technical_indicators", "missing_indicator", "no RSI/MACD on latest date")
            missing.append(sid)
    resolve_gaps(cur, "technical_indicators", "missing_indicator", set(ids) - set(missing))
    return missing


def detect_fundamentals(cur) -> list[int]:
    """Watchlist stocks with no full (non-PE-history) fundamentals row in the last 7 days."""
    ids = _watchlist_ids(cur)
    missing = []
    for sid in ids:
        cur.execute(
            "SELECT NOT EXISTS (SELECT 1 FROM fundamentals f WHERE f.stock_id=%s "
            "AND f.source <> 'screener_pe_history' AND f.date >= CURRENT_DATE - 7)", (sid,))
        if cur.fetchone()[0]:
            log_gap(cur, sid, "fundamentals", "stale_fundamentals", "no full row in last 7d")
            missing.append(sid)
    resolve_gaps(cur, "fundamentals", "stale_fundamentals", set(ids) - set(missing))
    return missing


def detect_news(cur) -> list[int]:
    """Watchlist stocks with no news_sentiment row in the last 7 days (availability-limited)."""
    ids = _watchlist_ids(cur)
    missing = []
    for sid in ids:
        cur.execute("SELECT NOT EXISTS (SELECT 1 FROM news_sentiment n WHERE n.stock_id=%s "
                    "AND n.date >= CURRENT_DATE - 7)", (sid,))
        if cur.fetchone()[0]:
            log_gap(cur, sid, "news_sentiment", "missing_news", "no news in last 7d")
            missing.append(sid)
    resolve_gaps(cur, "news_sentiment", "missing_news", set(ids) - set(missing))
    return missing


def detect_shareholding(cur) -> list[int]:
    """Watchlist stocks with no shareholding_pattern data."""
    ids = _watchlist_ids(cur)
    missing = []
    for sid in ids:
        cur.execute("SELECT NOT EXISTS (SELECT 1 FROM shareholding_pattern sp WHERE sp.stock_id=%s)", (sid,))
        if cur.fetchone()[0]:
            log_gap(cur, sid, "shareholding_pattern", "missing_shareholding", "no shareholding data")
            missing.append(sid)
    resolve_gaps(cur, "shareholding_pattern", "missing_shareholding", set(ids) - set(missing))
    return missing


def detect_signals(cur) -> list[int]:
    """Watchlist stocks with no composite_score for today."""
    ids = _watchlist_ids(cur)
    missing = []
    for sid in ids:
        cur.execute("SELECT NOT EXISTS (SELECT 1 FROM stock_scores sc WHERE sc.stock_id=%s "
                    "AND sc.composite_score IS NOT NULL AND sc.date=CURRENT_DATE)", (sid,))
        if cur.fetchone()[0]:
            log_gap(cur, sid, "stock_scores", "missing_score", "no composite_score today")
            missing.append(sid)
    resolve_gaps(cur, "stock_scores", "missing_score", set(ids) - set(missing))
    return missing


DETECTORS = {
    "ohlcv": detect_ohlcv, "indicators": detect_indicators, "fundamentals": detect_fundamentals,
    "news": detect_news, "shareholding": detect_shareholding, "signals": detect_signals,
}


# ── completeness scoring ──────────────────────────────────────────────────────

def _completeness_for(cur, sid: int) -> tuple[float, dict]:
    elements = {}
    cur.execute("SELECT EXISTS (SELECT 1 FROM daily_prices WHERE stock_id=%s AND date >= CURRENT_DATE - 7)", (sid,))
    elements["price"] = cur.fetchone()[0]
    cur.execute("""SELECT EXISTS (SELECT 1 FROM technical_indicators ti WHERE ti.stock_id=%s
                   AND ti.rsi_14 IS NOT NULL AND ti.macd IS NOT NULL
                   AND ti.date=(SELECT MAX(date) FROM daily_prices dp WHERE dp.stock_id=%s))""", (sid, sid))
    elements["indicators"] = cur.fetchone()[0]
    cur.execute("SELECT EXISTS (SELECT 1 FROM stock_scores WHERE stock_id=%s AND composite_score IS NOT NULL)", (sid,))
    elements["signals"] = cur.fetchone()[0]
    cur.execute("SELECT EXISTS (SELECT 1 FROM fundamentals WHERE stock_id=%s AND source <> 'screener_pe_history')", (sid,))
    elements["fundamentals"] = cur.fetchone()[0]
    cur.execute("SELECT EXISTS (SELECT 1 FROM shareholding_pattern WHERE stock_id=%s)", (sid,))
    elements["shareholding"] = cur.fetchone()[0]
    cur.execute("SELECT EXISTS (SELECT 1 FROM news_sentiment WHERE stock_id=%s AND date >= CURRENT_DATE - 30)", (sid,))
    elements["news"] = cur.fetchone()[0]
    score = sum(w for k, w in COMPLETENESS_WEIGHTS.items() if elements.get(k))
    return float(score), elements


def update_completeness_scores(watchlist: str = WATCHLIST) -> dict:
    """Compute + store data_completeness_score for all watchlist stocks. Returns summary."""
    conn = get_conn()
    cur = conn.cursor()
    ids = _watchlist_ids(cur)
    today = date.today()
    below_80 = []
    for sid in ids:
        score, _ = _completeness_for(cur, sid)
        cur.execute("""
            INSERT INTO stock_scores (stock_id, date, data_completeness_score)
            VALUES (%s, %s, %s)
            ON CONFLICT (stock_id, date) DO UPDATE SET data_completeness_score = EXCLUDED.data_completeness_score
        """, (sid, today, score))
        if score < 80:
            cur.execute("SELECT tradingsymbol FROM stocks WHERE id=%s", (sid,))
            below_80.append((cur.fetchone()[0], score))
    conn.commit()
    cur.close()
    conn.close()
    return {"scored": len(ids), "below_80": below_80}


# ── audit orchestration (called by post_run_audit asset) ──────────────────────

def run_audit(domain: str) -> dict:
    """Detect gaps for a job's domain, update completeness, and log a STATUS.md note
    if any stock is below 80% complete."""
    conn = get_conn()
    cur = conn.cursor()
    gaps = {}
    for name in DOMAIN_DETECTORS.get(domain, list(DETECTORS)):
        gaps[name] = DETECTORS[name](cur)
    conn.commit()
    cur.close()
    conn.close()

    comp = update_completeness_scores()
    total_gaps = sum(len(v) for v in gaps.values())
    summary = {"domain": domain, "gaps": {k: len(v) for k, v in gaps.items()},
               "total_gaps": total_gaps, "completeness": comp}

    if comp["below_80"]:
        _append_status(domain, summary, comp["below_80"])
    return summary


def unresolved_gaps(older_than_minutes: int = 60) -> list[dict]:
    """Open gaps detected more than N minutes ago — what the sensor acts on."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, stock_id, table_name, gap_type FROM data_quality_log "
        "WHERE resolved_at IS NULL AND detected_at < now() - (%s || ' minutes')::interval "
        "ORDER BY detected_at", (older_than_minutes,))
    rows = [{"id": r[0], "stock_id": r[1], "table_name": r[2], "gap_type": r[3]} for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def fill_gaps(gaps: list[dict] = None, max_retries: int = 2) -> dict:
    """Targeted gap fill — re-run only what's needed for the affected stocks, not full
    jobs. `gaps` is a list from unresolved_gaps() (else all open gaps are filled).
    Per-stock for ohlcv/indicators/fundamentals; collector-level for news/scores
    (proactive/cheap). Increments retry_count on data_refresh_log per source.
    """
    conn = get_conn()
    cur = conn.cursor()
    if gaps is None:
        cur.execute("SELECT stock_id, table_name, gap_type FROM data_quality_log WHERE resolved_at IS NULL")
        gaps = [{"stock_id": r[0], "table_name": r[1], "gap_type": r[2]} for r in cur.fetchall()]

    by_type: dict[str, list[int]] = {}
    for g in gaps:
        by_type.setdefault(g["gap_type"], []).append(g["stock_id"])

    def symbols(ids):
        cur.execute("SELECT id, tradingsymbol FROM stocks WHERE id = ANY(%s)", (ids,))
        return cur.fetchall()

    filled = {}

    if "missing_ohlcv" in by_type:
        from data_collectors.backfill_watchlist_prices import backfill_stale_watchlist_prices
        r = backfill_stale_watchlist_prices(days=30)
        filled["missing_ohlcv"] = r.get("stocks_filled", 0)
        _bump_retry("nse_ohlcv")

    if "missing_indicator" in by_type:
        from analysis.calculate_indicators import calculate_all_indicators
        n = 0
        for sid, sym in symbols([s for s in by_type["missing_indicator"] if s]):
            try:
                calculate_all_indicators(sid, sym); n += 1
            except Exception:  # noqa: BLE001
                pass
        filled["missing_indicator"] = n
        _bump_retry("tech_indicators")

    if "stale_fundamentals" in by_type:
        from data_collectors.screener_collector import fetch_screener_data, upsert_fundamentals
        n = 0
        for sid, sym in symbols([s for s in by_type["stale_fundamentals"] if s]):
            try:
                if upsert_fundamentals(sid, sym, fetch_screener_data(sym)):
                    n += 1
            except Exception:  # noqa: BLE001
                pass
        filled["stale_fundamentals"] = n
        _bump_retry("screener")

    if "missing_shareholding" in by_type:
        from data_collectors.shareholding_collector import collect_shareholding
        try:
            collect_shareholding()
        except Exception:  # noqa: BLE001
            pass
        filled["missing_shareholding"] = "collector re-run"
        _bump_retry("shareholding_pattern")

    if "missing_news" in by_type:
        from data_collectors.news_collector import collect_news
        try:
            collect_news()
        except Exception:  # noqa: BLE001
            pass
        filled["missing_news"] = "collector re-run"
        _bump_retry("news_sentiment")

    if "missing_score" in by_type:
        from jobs.model_refresh import refresh_signal_scores
        try:
            refresh_signal_scores()
        except Exception:  # noqa: BLE001
            pass
        filled["missing_score"] = "scores re-run"
        _bump_retry("signals")

    cur.close()
    conn.close()

    # Re-detect to resolve fixed gaps + refresh completeness.
    conn = get_conn(); cur = conn.cursor()
    for name in DETECTORS:
        DETECTORS[name](cur)
    conn.commit(); cur.close(); conn.close()
    update_completeness_scores()
    return {"filled": filled}


def _bump_retry(source: str):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("UPDATE data_refresh_log SET retry_count = COALESCE(retry_count,0)+1, status='retrying' "
                "WHERE source=%s", (source,))
    conn.commit(); cur.close(); conn.close()


def gap_counts_by_table() -> dict:
    """Open-gap counts per table — for the Data Sources page."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT table_name, COUNT(*) FROM data_quality_log WHERE resolved_at IS NULL GROUP BY table_name")
    out = {r[0]: r[1] for r in cur.fetchall()}
    cur.close()
    conn.close()
    return out


def _append_status(domain, summary, below_80):
    """Append an audit note to STATUS.md when stocks fall below 80% completeness."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "STATUS.md")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"\n### Data quality audit — {domain} @ {ts}",
             f"- gaps: {summary['gaps']} (total {summary['total_gaps']})",
             f"- {len(below_80)} stock(s) below 80% completeness: "
             + ", ".join(f"{s}({int(sc)})" for s, sc in sorted(below_80, key=lambda x: x[1])[:30])]
    try:
        with open(path, "a") as f:
            f.write("\n".join(lines) + "\n")
    except Exception:
        pass
