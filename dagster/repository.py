"""
dagster/repository.py — thin orchestration entrypoint for the stock-analyzer code location.

Assets live in dagster/assets/{kite_infra,nse_daily,nse_weekly,nse_monthly,us_daily,us_weekly}.py.
Jobs in dagster/jobs.py, schedules in dagster/schedules.py, sensors in dagster/sensors.py.
This file only imports them and assembles Definitions.

Path note: dagster/ is put first on sys.path so sibling modules import by bare name
(jobs, schedules, sensors, assets.*); the project root is second so the collector
packages resolve. See dagster/assets/__init__.py for the rationale.

Quick reference:
  dagster dev -w workspace.yaml                         # UI at localhost:3000
  dagster asset materialize -f dagster/repository.py --select nse_fii_dii_flows
  dagster job execute -f dagster/repository.py --job nse_daily_job
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from dagster import Definitions  # noqa: E402

from assets.kite_infra import kite_token_refreshed  # noqa: E402
from assets.nse_daily import (  # noqa: E402
    nse_raw_prices, nse_technical_indicators, nse_fii_dii_flows, nse_corporate_actions,
    nse_news_sentiment, nse_fno_data, nse_block_deals, bse_bulk_deals, nse_signals,
    nse_daily_audit, india_fear_greed,
)
from assets.nse_weekly import (  # noqa: E402
    nse_stock_universe, nse_fundamentals, nse_macro_indicators, nse_insider_trades,
    nse_shareholding_pattern, nse_expiry_calendar, nse_google_trends, nse_weekly_audit,
    nse_quarterly_financials, nse_analyst_targets, nse_pledging_alerts, nse_sast_disclosures,
)
from assets.nse_monthly import nse_model_refresh, nse_mf_holdings  # noqa: E402
from assets.maintenance import nse_indicator_recompute, nse_gap_fill  # noqa: E402
from assets.us_daily import us_raw_prices, us_insider_trades, us_signals, us_fear_greed  # noqa: E402
from assets.us_weekly import us_macro, us_13f_holdings  # noqa: E402
from assets.notifications import telegram_daily_digest  # noqa: E402

from jobs import ALL_JOBS  # noqa: E402
from schedules import ALL_SCHEDULES  # noqa: E402
from sensors import ALL_SENSORS  # noqa: E402

defs = Definitions(
    assets=[
        # kite_infra
        kite_token_refreshed,
        # nse_daily
        nse_raw_prices, nse_technical_indicators, nse_fii_dii_flows, nse_corporate_actions,
        nse_news_sentiment, nse_fno_data, nse_block_deals, bse_bulk_deals, nse_signals,
        nse_daily_audit, india_fear_greed,
        # nse_weekly
        nse_stock_universe, nse_fundamentals, nse_macro_indicators, nse_insider_trades,
        nse_shareholding_pattern, nse_expiry_calendar, nse_google_trends, nse_weekly_audit,
        nse_quarterly_financials, nse_analyst_targets, nse_pledging_alerts, nse_sast_disclosures,
        # nse_monthly
        nse_model_refresh, nse_mf_holdings,
        # maintenance
        nse_indicator_recompute, nse_gap_fill,
        # us_daily
        us_raw_prices, us_insider_trades, us_signals, us_fear_greed,
        # us_weekly
        us_macro, us_13f_holdings,
        # notifications
        telegram_daily_digest,
    ],
    jobs=ALL_JOBS,
    schedules=ALL_SCHEDULES,
    sensors=ALL_SENSORS,
)
