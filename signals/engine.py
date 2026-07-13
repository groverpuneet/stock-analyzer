"""Signal engine orchestrator — run all pillars, combine per horizon, persist.

Public entry points:
  run_signals(stock_ids=None, watchlist='Default', skip_external=False) -> summary dict
  compute_for_stock(conn, stock_id, ...) -> per-stock computed pillars + horizons
"""
import time
from datetime import date, datetime, timedelta

from psycopg2.extras import Json

from .util import get_conn, dict_cur, f
from .technical import score_technical
from .fundamental import score_fundamental
from .flows import score_flows
from .external import fetch_external_sentiment, score_external
from .advisor import score_advisor
from .combiner import combine

HORIZONS = ["SHORT", "MID", "LONG"]
CACHE_HOURS = 6


def _cached_external(conn, stock_id):
    with dict_cur(conn) as cur:
        cur.execute(
            "SELECT cached_external_sentiment, external_cache_expiry FROM signal_explanations "
            "WHERE stock_id=%s AND cached_external_sentiment IS NOT NULL "
            "ORDER BY external_cache_expiry DESC NULLS LAST LIMIT 1", (stock_id,))
        row = cur.fetchone()
    if row and row["external_cache_expiry"] and row["external_cache_expiry"] > datetime.now():
        return row["cached_external_sentiment"], row["external_cache_expiry"]
    return None, None


def _merge_metrics(pillars: dict) -> dict:
    out = {}
    for name, p in pillars.items():
        for k, v in (p.get("key_metrics") or {}).items():
            out[f"{name[:4]}.{k}"] = v
    return out


def compute_for_stock(conn, stock_id: int, skip_external: bool = False,
                       as_of: date | None = None) -> dict | None:
    as_of = as_of or date.today()
    is_live = as_of >= date.today()
    with dict_cur(conn) as cur:
        cur.execute("SELECT tradingsymbol, name FROM stocks WHERE id=%s", (stock_id,))
        s = cur.fetchone()
    if not s:
        return None

    tech = score_technical(conn, stock_id, as_of)
    fund = score_fundamental(conn, stock_id, as_of)
    flow = score_flows(conn, stock_id, as_of)
    adv = score_advisor(conn, stock_id, as_of)

    # External sentiment is a live web/news fetch — it has no historical replay, so a
    # past as_of always skips it (no look-ahead, and no point re-fetching "current" news).
    raw, expiry = (None, None)
    fetched = False
    if is_live:
        raw, expiry = _cached_external(conn, stock_id)
        if raw is None and not skip_external:
            raw = fetch_external_sentiment(s["name"], s["tradingsymbol"])
            expiry = datetime.now() + timedelta(hours=CACHE_HOURS)
            fetched = True
    ext = score_external(raw)

    pillars = {"technical": tech, "fundamental": fund, "flow": flow, "external": ext, "advisor": adv}
    key_metrics = _merge_metrics(pillars)
    horizons = {h: combine(h, pillars) for h in HORIZONS}
    return {
        "symbol": s["tradingsymbol"], "name": s["name"],
        "pillars": pillars, "key_metrics": key_metrics, "horizons": horizons,
        "external_raw": raw, "external_expiry": expiry, "external_fetched": fetched,
    }


def _store(conn, stock_id: int, computed: dict, as_of: date | None = None):
    today = as_of or date.today()
    p = computed["pillars"]
    with conn.cursor() as cur:
        for h in HORIZONS:
            c = computed["horizons"][h]
            cur.execute(
                """
                INSERT INTO signal_explanations
                    (stock_id, date, horizon, signal_type, strength, confidence, all_pillars_agree,
                     technical_score, technical_reasoning, fundamental_score, fundamental_reasoning,
                     flow_score, flow_reasoning, external_score, external_reasoning,
                     advisor_score, advisor_reasoning, overall_score, overall_reasoning,
                     key_metrics, contrary_indicators, what_would_change,
                     cached_external_sentiment, external_cache_expiry)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (stock_id, date, horizon) DO UPDATE SET
                    signal_type=EXCLUDED.signal_type, strength=EXCLUDED.strength,
                    confidence=EXCLUDED.confidence, all_pillars_agree=EXCLUDED.all_pillars_agree,
                    technical_score=EXCLUDED.technical_score, technical_reasoning=EXCLUDED.technical_reasoning,
                    fundamental_score=EXCLUDED.fundamental_score, fundamental_reasoning=EXCLUDED.fundamental_reasoning,
                    flow_score=EXCLUDED.flow_score, flow_reasoning=EXCLUDED.flow_reasoning,
                    external_score=EXCLUDED.external_score, external_reasoning=EXCLUDED.external_reasoning,
                    advisor_score=EXCLUDED.advisor_score, advisor_reasoning=EXCLUDED.advisor_reasoning,
                    overall_score=EXCLUDED.overall_score, overall_reasoning=EXCLUDED.overall_reasoning,
                    key_metrics=EXCLUDED.key_metrics, contrary_indicators=EXCLUDED.contrary_indicators,
                    what_would_change=EXCLUDED.what_would_change,
                    cached_external_sentiment=EXCLUDED.cached_external_sentiment,
                    external_cache_expiry=EXCLUDED.external_cache_expiry
                """,
                (
                    stock_id, today, h, c["signal_type"], c["strength"], c["confidence"], c["all_pillars_agree"],
                    p["technical"]["score"], Json(p["technical"]["reasoning"]),
                    p["fundamental"]["score"], Json(p["fundamental"]["reasoning"]),
                    p["flow"]["score"], Json(p["flow"]["reasoning"]),
                    p["external"]["score"], Json(p["external"]["reasoning"]),
                    p["advisor"]["score"], Json(p["advisor"]["reasoning"]),
                    c["overall_score"], Json(c["overall_reasoning"]),
                    Json(computed["key_metrics"]), Json(c["contrary_indicators"]), Json(c["what_would_change"]),
                    Json(computed["external_raw"]) if computed["external_raw"] is not None else None,
                    computed["external_expiry"],
                ),
            )
    conn.commit()


def run_signals(stock_ids: list[int] | None = None, watchlist: str = "Default",
                skip_external: bool = False, external_pause: float = 1.0,
                as_of: date | None = None) -> dict:
    as_of = as_of or date.today()
    conn = get_conn()
    try:
        if stock_ids is None:
            with dict_cur(conn) as cur:
                # listing_date IS NULL means unreconciled (SME/ETF/etc, not evidence of not-
                # yet-listed) — see survivorship_collector.py — so it's never excluded here.
                cur.execute(
                    "SELECT s.id FROM watchlist w JOIN stocks s ON w.stock_id=s.id "
                    "WHERE w.name=%s AND s.market <> 'MF' "
                    "AND (s.listing_date IS NULL OR s.listing_date <= %s) "
                    "ORDER BY s.tradingsymbol", (watchlist, as_of))
                stock_ids = [r["id"] for r in cur.fetchall()]

        done, fetched, totals = 0, 0, {"technical": [], "fundamental": [], "flow": [], "external": []}
        for sid in stock_ids:
            try:
                c = compute_for_stock(conn, sid, skip_external=skip_external, as_of=as_of)
                if not c:
                    continue
                _store(conn, sid, c, as_of)
                done += 1
                if c["external_fetched"]:
                    fetched += 1
                    if external_pause:
                        time.sleep(external_pause)  # be gentle on DDG/RSS
                for name in totals:
                    v = c["pillars"][name]["score"]
                    if v is not None:
                        totals[name].append(v)
            except Exception as e:  # noqa: BLE001
                print(f"  ✗ signal failed for stock {sid}: {e}")
        avg = {k: (round(sum(v) / len(v), 1) if v else None) for k, v in totals.items()}
        summary = {"stocks": done, "external_fetched": fetched, "avg_pillar_scores": avg}
        print(f"signals: {done} stocks · external fetched {fetched} · avg {avg}")
        return summary
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    run_signals(skip_external=("--no-external" in sys.argv))
