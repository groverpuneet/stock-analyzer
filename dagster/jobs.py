"""All Dagster job definitions.

Jobs select assets by group/asset name (strings), so this module doesn't import
the asset objects — keeping it import-light. Path bootstrap mirrors assets/.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))      # .../stock-analyzer/dagster
_ROOT = os.path.dirname(_HERE)                           # .../stock-analyzer
for _p in (_ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from dagster import define_asset_job, AssetSelection  # noqa: E402

kite_token_job = define_asset_job(
    name="kite_token_job",
    selection=AssetSelection.groups("kite_infra"),
    description="Daily Kite access token refresh via Playwright + pyotp. Runs before nse_daily_job.",
)

nse_daily_job = define_asset_job(
    name="nse_daily_job",
    selection=AssetSelection.groups("nse_daily"),
    description="Full NSE post-market pipeline: prices → indicators → FII/actions/news → signals.",
)

nse_news_job = define_asset_job(
    name="nse_news_job",
    selection=AssetSelection.assets("nse_news_sentiment"),
    description="News headlines + FinBERT sentiment only. Used by the watchlist change sensor.",
)

nse_weekly_job = define_asset_job(
    name="nse_weekly_job",
    selection=AssetSelection.groups("nse_weekly"),
    description="Sunday batch: universe expansion, Screener.in fundamentals, RBI macro, insider trades.",
)

nse_monthly_job = define_asset_job(
    name="nse_monthly_job",
    selection=AssetSelection.groups("nse_monthly"),
    description="1st of month: composite scores + FinBERT cache refresh + 52W indicator baselines.",
)

nse_fno_job = define_asset_job(
    name="nse_fno_job",
    selection=AssetSelection.assets("nse_fno_data"),
    description="F&O daily collection: India VIX + participant OI PCR. Runs at 16:45 IST.",
)

bse_bulk_job = define_asset_job(
    name="bse_bulk_job",
    selection=AssetSelection.assets("bse_bulk_deals"),
    description="Daily BSE/NSE bulk + block deals via NSE archive CSV. Runs 16:30 IST after market close.",
)

us_daily_job = define_asset_job(
    name="us_daily_job",
    selection=AssetSelection.groups("us_daily"),
    description="US daily pipeline: Polygon.io OHLCV + SEC Form 4 insider trades.",
)

us_weekly_job = define_asset_job(
    name="us_weekly_job",
    selection=AssetSelection.groups("us_weekly"),
    description="US weekly batch: FRED macro indicators (Fed rate, CPI, GDP, unemployment).",
)

ALL_JOBS = [
    kite_token_job, nse_daily_job, nse_news_job, nse_fno_job, bse_bulk_job,
    nse_weekly_job, nse_monthly_job, us_daily_job, us_weekly_job,
]
