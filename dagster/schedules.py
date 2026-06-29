"""All Dagster schedule definitions. Times in each job's market timezone."""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from dagster import ScheduleDefinition, DefaultScheduleStatus  # noqa: E402

from jobs import (  # noqa: E402  (dagster/jobs.py — dagster dir is first on sys.path)
    kite_token_job, nse_daily_job, nse_weekly_job, nse_monthly_job,
    nse_fno_job, bse_bulk_job, us_daily_job, us_weekly_job, telegram_digest_job,
)

_RUNNING = DefaultScheduleStatus.RUNNING   # all schedules enabled by default

kite_token_schedule = ScheduleDefinition(
    name="kite_token_daily",
    job=kite_token_job,
    cron_schedule="0 8 * * *",        # 08:00 IST daily
    execution_timezone="Asia/Kolkata",
    default_status=_RUNNING,
    description="Refresh Kite access token before NSE market open (09:15 IST).",
)

kite_token_retry_schedule = ScheduleDefinition(
    name="kite_token_retry",
    job=kite_token_job,
    cron_schedule="*/15 8-9 * * 1-5",   # every 15 min, 08:00-09:59 IST weekdays (give up at 10:00)
    execution_timezone="Asia/Kolkata",
    default_status=_RUNNING,
    description="Retry Kite token refresh every 15 min until 10 AM IST in case the 08:00 run failed.",
)

nse_daily_schedule = ScheduleDefinition(
    name="nse_daily_market",
    job=nse_daily_job,
    cron_schedule="0 16 * * 1-5",     # 16:00 IST Mon-Fri (NSE closes 15:30)
    execution_timezone="Asia/Kolkata",
    default_status=_RUNNING,
    description="Post-market NSE pipeline on trading days.",
)

nse_weekly_schedule = ScheduleDefinition(
    name="nse_weekly",
    job=nse_weekly_job,
    cron_schedule="30 7 * * 0",       # 07:30 IST Sunday
    execution_timezone="Asia/Kolkata",
    default_status=_RUNNING,
    description="Weekly Sunday batch before Indian market open.",
)

nse_monthly_schedule = ScheduleDefinition(
    name="nse_monthly",
    job=nse_monthly_job,
    cron_schedule="0 2 1 * *",        # 02:00 IST 1st of month
    execution_timezone="Asia/Kolkata",
    default_status=_RUNNING,
    description="Monthly model refresh on the 1st of each month.",
)

nse_fno_schedule = ScheduleDefinition(
    name="nse_fno_daily",
    job=nse_fno_job,
    cron_schedule="45 16 * * 1-5",    # 16:45 IST Mon-Fri
    execution_timezone="Asia/Kolkata",
    default_status=_RUNNING,
    description="Daily F&O data: India VIX + PCR (index/FII/total) from NSE archives.",
)

bse_bulk_schedule = ScheduleDefinition(
    name="bse_bulk_daily",
    job=bse_bulk_job,
    cron_schedule="30 16 * * 1-5",    # 16:30 IST Mon-Fri
    execution_timezone="Asia/Kolkata",
    default_status=_RUNNING,
    description="Daily bulk + block deal collection. BSE API is JS-blocked; uses NSE archive CSV fallback.",
)

us_daily_schedule = ScheduleDefinition(
    name="us_daily_market",
    job=us_daily_job,
    cron_schedule="30 16 * * 1-5",    # 16:30 EST Mon-Fri (30 min after NYSE close)
    execution_timezone="America/New_York",
    default_status=_RUNNING,
    description="US post-market pipeline: Polygon.io OHLCV + SEC Form 4.",
)

us_weekly_schedule = ScheduleDefinition(
    name="us_weekly",
    job=us_weekly_job,
    cron_schedule="0 7 * * 0",        # 07:00 EST Sunday
    execution_timezone="America/New_York",
    default_status=_RUNNING,
    description="Weekly US macro refresh from FRED (Fed rate, CPI, GDP, unemployment).",
)

telegram_digest_schedule = ScheduleDefinition(
    name="telegram_digest_daily",
    job=telegram_digest_job,
    cron_schedule="0 8 * * *",        # 08:00 IST daily (after kite_token_job at 08:00)
    execution_timezone="Asia/Kolkata",
    default_status=_RUNNING,
    description="Push the morning digest to Telegram every day at 08:00 IST.",
)

ALL_SCHEDULES = [
    kite_token_schedule, kite_token_retry_schedule, nse_daily_schedule, nse_fno_schedule,
    bse_bulk_schedule, nse_weekly_schedule, nse_monthly_schedule, us_daily_schedule, us_weekly_schedule,
    telegram_digest_schedule,
]
