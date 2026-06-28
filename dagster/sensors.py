"""Dagster sensors.

watchlist_change_sensor — polls every 60s for newly-added NSE watchlist stocks
that have no daily_prices in the last 30 days, logs them to watchlist_changes
(so each is handled once), and triggers, in order:
  nse_daily_job  →  nse_weekly_job  →  nse_news_job

Only exchange='NSE' equities/ETFs are considered: mutual-fund instruments carry
NAV (no OHLCV) and would otherwise look "missing" forever. The watchlist_changes
table is the dedupe ledger — once a stock has a row, it isn't re-triggered.
"""
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import psycopg2  # noqa: E402
from dagster import sensor, RunRequest, SkipReason, DefaultSensorStatus  # noqa: E402

from jobs import (  # noqa: E402
    nse_daily_job, nse_weekly_job, nse_news_job, nse_indicator_recompute_job,
)

DB_URL = os.environ.get("DATABASE_URL", "postgresql://puneetgrover@localhost/stock_analyzer")
WATCHLIST = "Default"

_NEW_STOCKS_SQL = """
    SELECT s.id, s.tradingsymbol
    FROM watchlist w
    JOIN stocks s ON w.stock_id = s.id
    WHERE w.name = %s
      AND s.exchange = 'NSE'
      AND NOT EXISTS (
        SELECT 1 FROM daily_prices dp
        WHERE dp.stock_id = s.id AND dp.date >= CURRENT_DATE - INTERVAL '30 days'
      )
      AND NOT EXISTS (
        SELECT 1 FROM watchlist_changes wc
        WHERE wc.stock_id = s.id AND wc.watchlist_name = %s
      )
    ORDER BY s.tradingsymbol
"""


@sensor(
    name="watchlist_change_sensor",
    minimum_interval_seconds=60,
    jobs=[nse_daily_job, nse_weekly_job, nse_news_job],
    default_status=DefaultSensorStatus.RUNNING,
    description=(
        "Every 60s: detect new NSE watchlist stocks with no prices in 30 days, "
        "log to watchlist_changes, and trigger nse_daily_job → nse_weekly_job → nse_news_job."
    ),
)
def watchlist_change_sensor(context):
    try:
        conn = psycopg2.connect(DB_URL)
    except Exception as e:  # noqa: BLE001
        return SkipReason(f"DB unreachable: {e}")

    try:
        cur = conn.cursor()
        cur.execute(_NEW_STOCKS_SQL, (WATCHLIST, WATCHLIST))
        new_stocks = cur.fetchall()  # [(stock_id, symbol), ...]

        if not new_stocks:
            cur.close()
            conn.close()
            return SkipReason("No new watchlist stocks needing a backfill.")

        symbols = [s for _, s in new_stocks]
        batch = str(int(time.time()))
        # run_key ties the three job runs to this detection batch (Dagster dedupes by run_key).
        run_keys = {j: f"wl-change-{batch}-{j}" for j in ("daily", "weekly", "news")}
        note = (f"auto-detected {len(new_stocks)} new watchlist stock(s): "
                f"{', '.join(symbols[:25])}{'…' if len(symbols) > 25 else ''}; "
                f"triggered nse_daily_job → nse_weekly_job → nse_news_job")

        # Ledger the changes (handled=true: we are triggering processing now).
        for stock_id, symbol in new_stocks:
            cur.execute(
                """
                INSERT INTO watchlist_changes
                    (stock_id, symbol, watchlist_name, detected_at, handled, handled_at, run_ids, notes)
                VALUES (%s, %s, %s, NOW(), TRUE, NOW(), %s, %s)
                ON CONFLICT (stock_id, watchlist_name) DO NOTHING
                """,
                (stock_id, symbol, WATCHLIST, ",".join(run_keys.values()), note),
            )
        conn.commit()
        cur.close()
        conn.close()

        context.log.info(note)
        # Yield in the required order: daily → weekly → news.
        tags = {"trigger": "watchlist_change_sensor", "new_stocks": str(len(new_stocks))}
        yield RunRequest(job_name=nse_daily_job.name, run_key=run_keys["daily"], tags=tags)
        yield RunRequest(job_name=nse_weekly_job.name, run_key=run_keys["weekly"], tags=tags)
        yield RunRequest(job_name=nse_news_job.name, run_key=run_keys["news"], tags=tags)
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        conn.close()
        return SkipReason(f"watchlist_change_sensor error: {e}")


@sensor(
    name="indicator_recompute_sensor",
    minimum_interval_seconds=300,
    job=nse_indicator_recompute_job,
    default_status=DefaultSensorStatus.RUNNING,
    description=(
        "Every 5 min: if recompute_queue is non-empty (stocks whose daily_prices changed), "
        "trigger nse_indicator_recompute_job to recompute their indicators and clear the queue. "
        "Safety net for prices that land outside the normal daily pipeline."
    ),
)
def indicator_recompute_sensor(context):
    try:
        conn = psycopg2.connect(DB_URL)
    except Exception as e:  # noqa: BLE001
        return SkipReason(f"DB unreachable: {e}")
    try:
        cur = conn.cursor()
        cur.execute("SELECT stock_id FROM recompute_queue ORDER BY stock_id")
        ids = [r[0] for r in cur.fetchall()]
        cur.close()
        conn.close()
    except Exception as e:  # noqa: BLE001
        conn.close()
        return SkipReason(f"indicator_recompute_sensor error: {e}")

    if not ids:
        return SkipReason("recompute_queue is empty.")
    # run_key keyed to the queued set — a still-running job (same set) won't re-trigger;
    # a new set of stocks gets a fresh run.
    run_key = "recompute-" + ",".join(str(i) for i in ids)
    context.log.info(f"recompute_queue has {len(ids)} stock(s) — triggering recompute.")
    return RunRequest(run_key=run_key, tags={"trigger": "indicator_recompute_sensor",
                                             "queued": str(len(ids))})


ALL_SENSORS = [watchlist_change_sensor, indicator_recompute_sensor]
