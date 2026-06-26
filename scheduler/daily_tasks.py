"""
scheduler/daily_tasks.py — unified multi-tier scheduler

Tiers and schedule (all IST):
  Daily     Mon-Fri  16:00   OHLCV prices (Kite)
  Daily     Mon-Fri  16:15   Technical indicators
  Daily     Mon-Fri  16:30   FII/DII flows
  Daily     Mon-Fri  16:45   NSE corporate actions + earnings calendar
  Daily     Mon-Fri  17:00   Signal report

  Weekly    Sunday   08:00   Screener.in fundamentals
  Weekly    Sunday   08:30   RBI macro indicators  ← moved from monthly
  Weekly    Sunday   09:00   Insider trades + Bulk deals
  Weekly    Sunday   09:30   Sector indices + Google Trends

  Monthly   1st Sun  06:00   Model refresh (scores + FinBERT + baselines)

  Quarterly  (manual trigger after results season)

Engineering note on why we have a central scheduler:
  Each collector could have its own cron job in crontab. But a single Python
  scheduler gives us: shared logging, dependency ordering (indicators after
  OHLCV), guards (needs_refresh), and one place to see all job statuses.
  The tradeoff is that if this process dies, everything stops. For production
  you'd use a proper job queue (Celery + Redis) or a managed scheduler
  (AWS EventBridge). For now, APScheduler is the right level of complexity.

Commands:
  python scheduler/daily_tasks.py              # live scheduler
  python scheduler/daily_tasks.py --test       # run all tasks right now
  python scheduler/daily_tasks.py --status     # show refresh log
  python scheduler/daily_tasks.py --screener   # run screener only
  python scheduler/daily_tasks.py --fii        # run FII/DII only
  python scheduler/daily_tasks.py --actions    # run NSE actions only
  python scheduler/daily_tasks.py --macro      # run RBI macro only
  python scheduler/daily_tasks.py --insider    # run insider trades + bulk deals only
  python scheduler/daily_tasks.py --model     # run monthly model refresh only
"""
import sys
import os
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_collectors.collect_watchlist_data import collect_data
from analysis.calculate_indicators import process_all_watchlist_stocks
from analysis.generate_signals import generate_daily_report
from data_collectors.fii_dii_collector import collect_fii_dii
from data_collectors.nse_actions_collector import collect_nse_actions
from data_collectors.screener_collector import collect_screener_fundamentals
from utils.db import get_refresh_status, needs_refresh
from data_collectors.insider_bulk_collector import collect_insider_and_bulk
from data_collectors.news_collector import collect_news
from jobs.model_refresh import run_model_refresh
from utils.logger import get_logger

log = get_logger(__name__)

IST = 'Asia/Kolkata'


# ── Task wrappers ──────────────────────────────────────────────────────────────
# Each wrapper:
#   1. Logs start and end with the scheduler logger
#   2. Catches exceptions so one failed task doesn't kill the scheduler
#   3. The actual collector handles its own refresh_log update + detailed logging

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


def task_nse_actions():
    log.info("=== TASK START: NSE corporate actions ===")
    try:
        collect_nse_actions()
        log.info("=== TASK DONE: NSE corporate actions ===")
    except Exception as e:
        log.error(f"=== TASK FAILED: NSE corporate actions — {e} ===", exc_info=True)


def task_screener():
    """Weekly — guarded against re-runs within 6 days."""
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
    """
    Weekly (moved from monthly) — RBI data including repo rate, CPI, IIP.
    Collector stub for now; full implementation in next session.
    """
    log.info("=== TASK START: RBI macro indicators ===")
    if not needs_refresh('rbi_macro', min_hours=6 * 24):
        log.info("RBI macro: skipping — ran within last 6 days")
        return
    log.warning("RBI macro collector not yet implemented — skipping")
    log.info("=== TASK DONE: RBI macro indicators (stub) ===")


def task_insider_bulk():
    """Weekly — insider trades + bulk deals, last 7 days."""
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
    """Monthly (first Sunday) — signal scores, FinBERT cache, indicator baselines."""
    log.info("=== TASK START: Monthly model refresh ===")
    if not needs_refresh('model_refresh', min_hours=20 * 24):
        log.info("Model refresh: skipping — ran within last 20 days")
        return
    try:
        run_model_refresh()
        log.info("=== TASK DONE: Monthly model refresh ===")
    except Exception as e:
        log.error(f"=== TASK FAILED: Model refresh — {e} ===", exc_info=True)


def task_sector_indices():
    """Weekly — Nifty sector index weights and Google Trends. Stub for now."""
    log.info("=== TASK START: Sector indices + Google Trends ===")
    if not needs_refresh('sector_indices', min_hours=6 * 24):
        log.info("Sector indices: skipping — ran within last 6 days")
        return
    log.warning("Sector indices collector not yet implemented — skipping")
    log.info("=== TASK DONE: Sector indices (stub) ===")


def task_whatsapp():
    """
    Daily 07:00 AM IST — before market open.
    Processes any .txt files dropped into whatsapp_exports/ overnight.
    Guards with needs_refresh so re-running manually won't double-process.
    """
    log.info("=== TASK START: WhatsApp signals ===")
    try:
        pass  # WhatsApp collector not yet deployed
        log.info("=== TASK DONE: WhatsApp signals ===")
    except Exception as e:
        log.error(f"=== TASK FAILED: WhatsApp — {e} ===", exc_info=True)


# ── Pipelines ──────────────────────────────────────────────────────────────────

def run_daily_pipeline():
    """Full daily pipeline — called by --test and can be called manually."""
    log.info("Starting daily pipeline")
    task_ohlcv()
    task_indicators()
    task_fii_dii()
    task_nse_actions()
    task_signals()
    task_whatsapp()
    log.info("Daily pipeline complete")


def run_weekly_pipeline():
    """Full weekly pipeline."""
    log.info("Starting weekly pipeline")
    task_screener()
    task_rbi_macro()
    task_insider_bulk()
    task_sector_indices()
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

    print(f"\n{'='*80}\n")


# ── Scheduler ──────────────────────────────────────────────────────────────────

def start_scheduler():
    scheduler = BlockingScheduler()

    jobs = [
        # ── Daily Mon-Fri ──────────────────────────────────────────────────────
        (task_ohlcv,          CronTrigger(day_of_week='mon-fri', hour=16, minute=0,  timezone=IST), 'daily_ohlcv'),
        (task_indicators,     CronTrigger(day_of_week='mon-fri', hour=16, minute=15, timezone=IST), 'daily_indicators'),
        (task_fii_dii,        CronTrigger(day_of_week='mon-fri', hour=16, minute=30, timezone=IST), 'daily_fii_dii'),
        (task_nse_actions,    CronTrigger(day_of_week='mon-fri', hour=16, minute=45, timezone=IST), 'event_nse_actions'),
        (task_signals,        CronTrigger(day_of_week='mon-fri', hour=17, minute=0,  timezone=IST), 'daily_signals'),
        (task_news_sentiment, CronTrigger(day_of_week='mon-fri', hour=17, minute=15, timezone=IST), 'daily_news_sentiment'),

        # ── Pre-market Daily ──────────────────────────────────────────────────
        (task_whatsapp,       CronTrigger(day_of_week='mon-fri', hour=7,   minute=0,  timezone=IST), 'daily_whatsapp'),

        # ── Monthly first Sunday ───────────────────────────────────────────────
        (task_model_refresh,  CronTrigger(day_of_week='sun', day='1-7', hour=6, minute=0, timezone=IST), 'monthly_model_refresh'),

        # ── Weekly Sunday ──────────────────────────────────────────────────────
        (task_screener,       CronTrigger(day_of_week='sun', hour=8,  minute=0,  timezone=IST), 'weekly_screener'),
        (task_rbi_macro,      CronTrigger(day_of_week='sun', hour=8,  minute=30, timezone=IST), 'weekly_rbi_macro'),
        (task_insider_bulk,   CronTrigger(day_of_week='sun', hour=9,  minute=0,  timezone=IST), 'weekly_insider_bulk'),
        (task_sector_indices, CronTrigger(day_of_week='sun', hour=9,  minute=30, timezone=IST), 'weekly_sectors'),
    ]

    for fn, trigger, job_id in jobs:
        scheduler.add_job(fn, trigger, id=job_id, replace_existing=True)

    log.info("Scheduler started")
    print(f"\n{'='*60}")
    print("SCHEDULER RUNNING  (Ctrl+C to stop)")
    print(f"{'='*60}")
    print("  Daily   Mon-Fri  16:00  OHLCV prices")
    print("  Daily   Mon-Fri  16:15  Technical indicators")
    print("  Daily   Mon-Fri  16:30  FII/DII flows")
    print("  Daily   Mon-Fri  16:45  NSE corporate actions")
    print("  Daily   Mon-Fri  17:00  Signal report")
    print("  Monthly 1st Sun  06:00  Model refresh (scores + FinBERT + baselines)")
    print("  Weekly  Sunday   08:00  Screener.in fundamentals")
    print("  Weekly  Sunday   08:30  RBI macro indicators")
    print("  Weekly  Sunday   09:00  Insider trades + Bulk deals")
    print("  Weekly  Sunday   09:30  Sector indices")
    print(f"{'='*60}\n")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped by user")
        print("\nScheduler stopped")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]

    if '--status' in args:
        print_status()
    elif '--test' in args:
        log.info("Running full test pipeline")
        run_daily_pipeline()
        run_weekly_pipeline()
        print_status()
    elif '--screener' in args:
        task_screener()
    elif '--fii' in args:
        task_fii_dii()
    elif '--actions' in args:
        task_nse_actions()
    elif '--macro' in args:
        task_rbi_macro()
    elif '--insider' in args:
        task_insider_bulk()
    elif '--model' in args:
        task_model_refresh()
    elif '--whatsapp' in args:
        task_whatsapp()
    elif '--daily' in args:
        run_daily_pipeline()
    elif '--weekly' in args:
        run_weekly_pipeline()
    else:
        start_scheduler()
