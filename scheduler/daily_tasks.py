"""
scheduler/daily_tasks.py — direct task runner and status monitor

APScheduler has been replaced by Dagster. Schedules now live in dagster/repository.py.
This file keeps its CLI flags as convenience wrappers for manual one-off runs,
debugging, and backfill — without needing to open the Dagster UI.

Dagster equivalents for each flag:
  --status          →  python scheduler/daily_tasks.py --status  (still the fastest way)
  --kite-token      →  dagster job execute -f dagster/repository.py --job kite_token_job
  --fii             →  dagster asset materialize -f dagster/repository.py --select nse_fii_dii_flows
  --fno             →  dagster asset materialize -f dagster/repository.py --select nse_fno_data
  --actions         →  dagster asset materialize -f dagster/repository.py --select nse_corporate_actions
  --screener        →  dagster asset materialize -f dagster/repository.py --select nse_fundamentals
  --macro           →  dagster asset materialize -f dagster/repository.py --select nse_macro_indicators
  --insider         →  dagster asset materialize -f dagster/repository.py --select nse_insider_trades
  --news            →  dagster asset materialize -f dagster/repository.py --select nse_news_sentiment
  --expand-universe →  dagster asset materialize -f dagster/repository.py --select nse_stock_universe
  --model-refresh   →  dagster job execute -f dagster/repository.py --job nse_monthly_job
  --daily           →  dagster job execute -f dagster/repository.py --job nse_daily_job
  --weekly          →  dagster job execute -f dagster/repository.py --job nse_weekly_job

Start Dagster:
  dagster dev -w workspace.yaml           # local dev — UI at localhost:3000
  docker compose up --build               # full Docker stack

Commands:
  python scheduler/daily_tasks.py --status           # show data_refresh_log
  python scheduler/daily_tasks.py --kite-token       # refresh Kite access token
  python scheduler/daily_tasks.py --fii              # run FII/DII only
  python scheduler/daily_tasks.py --fno              # run F&O data (VIX + PCR)
  python scheduler/daily_tasks.py --actions          # run NSE actions only
  python scheduler/daily_tasks.py --screener         # run screener only
  python scheduler/daily_tasks.py --macro            # run RBI macro only
  python scheduler/daily_tasks.py --insider          # run insider trades + bulk deals only
  python scheduler/daily_tasks.py --news             # run news sentiment only
  python scheduler/daily_tasks.py --expand-universe  # sync full NSE EQ instrument list
  python scheduler/daily_tasks.py --model-refresh    # run monthly model refresh
  python scheduler/daily_tasks.py --daily            # run full daily pipeline
  python scheduler/daily_tasks.py --weekly           # run full weekly pipeline
"""
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_collectors.collect_watchlist_data import collect_data
from analysis.calculate_indicators import process_all_watchlist_stocks
from analysis.generate_signals import generate_daily_report
from data_collectors.fii_dii_collector import collect_fii_dii
from data_collectors.fno_collector import collect_fno_data
from data_collectors.nse_actions_collector import collect_nse_actions
from data_collectors.screener_collector import collect_screener_fundamentals
from utils.db import get_refresh_status, needs_refresh
from data_collectors.insider_bulk_collector import collect_insider_and_bulk
from data_collectors.news_collector import collect_news
from data_collectors.expand_stock_universe import run_expand_universe
from kite_auth.auto_login import refresh_token as kite_refresh_token
from jobs.model_refresh import run_model_refresh
from utils.logger import get_logger

log = get_logger(__name__)


# ── Task wrappers ──────────────────────────────────────────────────────────────

def task_ohlcv():
    log.info("=== TASK START: OHLCV prices ===")
    from utils.db import refresh_log
    try:
        with refresh_log('kite_ohlcv') as rl:
            collect_data(watchlist_name='Default', days=5, include_quotes=True)
            rl['rows'] = 10
        log.info("=== TASK DONE: OHLCV prices ===")
    except Exception as e:
        log.error(f"=== TASK FAILED: OHLCV prices — {e} ===", exc_info=True)


def task_indicators():
    log.info("=== TASK START: Technical indicators ===")
    from utils.db import refresh_log
    try:
        with refresh_log('tech_indicators') as rl:
            process_all_watchlist_stocks()
            rl['rows'] = 10
        log.info("=== TASK DONE: Technical indicators ===")
    except Exception as e:
        log.error(f"=== TASK FAILED: Technical indicators — {e} ===", exc_info=True)


def task_signals():
    log.info("=== TASK START: Signal report ===")
    from utils.db import refresh_log
    try:
        with refresh_log('signals') as rl:
            generate_daily_report()
            rl['rows'] = 1
        log.info("=== TASK DONE: Signal report ===")
    except Exception as e:
        log.error(f"=== TASK FAILED: Signal report — {e} ===", exc_info=True)


def task_fii_dii():
    log.info("=== TASK START: FII/DII flows ===")
    try:
        collect_fii_dii()
        log.info("=== TASK DONE: FII/DII flows ===")
    except Exception as e:
        log.error(f"=== TASK FAILED: FII/DII flows — {e} ===", exc_info=True)


def task_fno():
    log.info("=== TASK START: F&O data ===")
    try:
        result = collect_fno_data()
        log.info(f"=== TASK DONE: F&O data — {result} ===")
    except Exception as e:
        log.error(f"=== TASK FAILED: F&O data — {e} ===", exc_info=True)


def task_nse_actions():
    log.info("=== TASK START: NSE corporate actions ===")
    try:
        collect_nse_actions()
        log.info("=== TASK DONE: NSE corporate actions ===")
    except Exception as e:
        log.error(f"=== TASK FAILED: NSE corporate actions — {e} ===", exc_info=True)


def task_screener():
    log.info("=== TASK START: Screener.in fundamentals ===")
    if not needs_refresh('screener', min_hours=6 * 24):
        log.info("Screener: skipping — ran within last 6 days")
        return
    try:
        collect_screener_fundamentals()
        log.info("=== TASK DONE: Screener.in fundamentals ===")
    except Exception as e:
        log.error(f"=== TASK FAILED: Screener — {e} ===", exc_info=True)


def task_news_sentiment():
    log.info("=== TASK START: News sentiment ===")
    try:
        collect_news()
        log.info("=== TASK DONE: News sentiment ===")
    except Exception as e:
        log.error(f"=== TASK FAILED: News sentiment — {e} ===", exc_info=True)


def task_rbi_macro():
    log.info("=== TASK START: RBI macro indicators ===")
    if not needs_refresh('rbi_macro', min_hours=6 * 24):
        log.info("RBI macro: skipping — ran within last 6 days")
        return
    try:
        from data_collectors.rbi_macro_collector import collect_rbi_macro
        collect_rbi_macro()
        log.info("=== TASK DONE: RBI macro indicators ===")
    except Exception as e:
        log.error(f"=== TASK FAILED: RBI macro — {e} ===", exc_info=True)


def task_insider_bulk():
    log.info("=== TASK START: Insider trades + Bulk deals ===")
    if not needs_refresh('insider_trades', min_hours=6 * 24):
        log.info("Insider/bulk: skipping — ran within last 6 days")
        return
    try:
        collect_insider_and_bulk(days=7)
        log.info("=== TASK DONE: Insider trades + Bulk deals ===")
    except Exception as e:
        log.error(f"=== TASK FAILED: Insider/bulk — {e} ===", exc_info=True)


def task_model_refresh():
    log.info("=== TASK START: Monthly model refresh ===")
    if not needs_refresh('model_refresh', min_hours=20 * 24):
        log.info("Model refresh: skipping — ran within last 20 days")
        return
    try:
        run_model_refresh()
        log.info("=== TASK DONE: Monthly model refresh ===")
    except Exception as e:
        log.error(f"=== TASK FAILED: Model refresh — {e} ===", exc_info=True)


def task_expand_universe():
    log.info("=== TASK START: Expand stock universe ===")
    if not needs_refresh('stock_universe', min_hours=6 * 24):
        log.info("Stock universe: skipping — ran within last 6 days")
        return
    try:
        run_expand_universe()
        log.info("=== TASK DONE: Expand stock universe ===")
    except Exception as e:
        log.error(f"=== TASK FAILED: Expand stock universe — {e} ===", exc_info=True)


def task_kite_token():
    log.info("=== TASK START: Kite token refresh ===")
    try:
        kite_refresh_token()
        log.info("=== TASK DONE: Kite token refresh ===")
    except Exception as e:
        log.error(f"=== TASK FAILED: Kite token refresh — {e} ===", exc_info=True)


# ── Pipelines ──────────────────────────────────────────────────────────────────

def run_daily_pipeline():
    log.info("Starting daily pipeline")
    task_ohlcv()
    task_indicators()
    task_fii_dii()
    task_nse_actions()
    task_signals()
    log.info("Daily pipeline complete")


def run_weekly_pipeline():
    log.info("Starting weekly pipeline")
    task_expand_universe()
    task_screener()
    task_rbi_macro()
    task_insider_bulk()
    log.info("Weekly pipeline complete")


# ── Status display ─────────────────────────────────────────────────────────────

def print_status():
    rows = get_refresh_status()
    print(f"\n{'='*80}")
    print(f"{'DATA REFRESH STATUS':^80}")
    print(f"{'='*80}")
    print(f"  {'Source':<24} {'Tier':<10} {'Status':<12} {'Last run':<22} {'Rows':>6}")
    print(f"  {'-'*74}")

    current_tier = None
    for r in rows:
        if r['tier'] != current_tier:
            current_tier = r['tier']
            print(f"\n  [{current_tier.upper()}]")

        last = str(r['completed_at'])[:16] if r['completed_at'] else 'never'
        status_icon = {'success': '✓', 'error': '✗', 'running': '⟳',
                       'never_run': '—', 'pending': 'ʷ'}.get(r['status'], '?')
        err = f"  ← {r['error_message'][:35]}" if r['status'] == 'error' and r['error_message'] else ''
        print(f"  {status_icon} {r['source']:<23} {r['tier']:<10} {r['status']:<12} {last:<22} {r['rows_upserted']:>6}{err}")

    print(f"\n{'='*80}")
    print("Scheduler: Dagster  |  UI: http://localhost:3000  |  dagster dev -w workspace.yaml")
    print(f"{'='*80}\n")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]

    if '--status' in args:
        print_status()
    elif '--kite-token' in args:
        task_kite_token()
    elif '--screener' in args:
        task_screener()
    elif '--fii' in args:
        task_fii_dii()
    elif '--fno' in args:
        task_fno()
    elif '--actions' in args:
        task_nse_actions()
    elif '--macro' in args:
        task_rbi_macro()
    elif '--expand-universe' in args:
        task_expand_universe()
    elif '--insider' in args:
        task_insider_bulk()
    elif '--model-refresh' in args:
        task_model_refresh()
    elif '--news' in args:
        task_news_sentiment()
    elif '--daily' in args:
        run_daily_pipeline()
    elif '--weekly' in args:
        run_weekly_pipeline()
    else:
        print(f"""
{'='*60}
STOCK ANALYZER — Task Runner
{'='*60}

The scheduler is now Dagster. To start it:

  dagster dev -w workspace.yaml      # local dev (UI at localhost:3000)
  docker compose up --build          # full Docker stack

Manual task flags (for debugging / backfill):
  --status           show data refresh log
  --kite-token       refresh Kite access token
  --fii              FII/DII flows
  --fno              F&O data (India VIX + PCR from NSE archives)
  --actions          NSE corporate actions
  --screener         Screener.in fundamentals
  --macro            RBI macro indicators
  --insider          insider trades + bulk deals
  --news             news sentiment (FinBERT)
  --expand-universe  sync full NSE EQ instrument list
  --model-refresh    monthly model refresh
  --daily            full daily pipeline
  --weekly           full weekly pipeline
{'='*60}
""")
