"""
dagster/repository.py — Dagster asset graph for stock-analyzer

All collector logic stays in data_collectors/, analysis/, jobs/, kite_auth/.
This file ONLY wraps those functions in @asset decorators and wires schedules.
No collector code was changed.

Asset dependency graph:
  kite_token_refreshed  (kite_infra group — 8am IST daily)

  nse_raw_prices                             ─┐
    └─> nse_technical_indicators              │  nse_daily group
  nse_fii_dii_flows                          │  16:00 IST Mon-Fri
  nse_corporate_actions                      │
  nse_news_sentiment                         │
  [all four] ─> nse_signals                 ─┘

  nse_stock_universe                         ─┐
  nse_fundamentals                            │  nse_weekly group
  nse_macro_indicators                        │  07:30 IST Sunday
  nse_insider_trades                         ─┘

  nse_model_refresh                          ─┐  nse_monthly group
                                             ─┘  02:00 IST 1st of month

  us_raw_prices                              ─┐  us_daily group
    └─> us_signals                           ─┘  16:30 EST Mon-Fri (placeholder)

Quick reference:
  dagster dev                                          # UI at localhost:3000
  dagster asset materialize -f dagster/repository.py --select nse_fii_dii_flows
  dagster job execute -f dagster/repository.py --job nse_daily_job
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dagster import (
    asset,
    define_asset_job,
    ScheduleDefinition,
    Definitions,
    AssetSelection,
)


# ── Kite Infrastructure ────────────────────────────────────────────────────────

@asset(
    group_name="kite_infra",
    description="Daily Kite Connect access token via Playwright + pyotp. Saved to .kite_access_token.",
)
def kite_token_refreshed(context) -> None:
    from kite_auth.auto_login import refresh_token
    refresh_token()
    context.log.info("Kite token refreshed and saved to .kite_access_token")


# ── NSE Daily Assets ──────────────────────────────────────────────────────────

@asset(
    group_name="nse_daily",
    description="OHLCV daily prices + live quotes for watchlist stocks via Kite Connect.",
)
def nse_raw_prices(context) -> None:
    from data_collectors.collect_watchlist_data import collect_data
    collect_data(watchlist_name="Default", days=5, include_quotes=True)


@asset(
    group_name="nse_daily",
    deps=[nse_raw_prices],
    description="RSI, SMA-20/50/200, EMA-12/26, MACD, Bollinger Bands computed from daily_prices.",
)
def nse_technical_indicators(context) -> None:
    from analysis.calculate_indicators import process_all_watchlist_stocks
    process_all_watchlist_stocks()


@asset(
    group_name="nse_daily",
    description="FII/DII net flows from NSE API (₹ Crore). Falls back to Moneycontrol scrape.",
)
def nse_fii_dii_flows(context) -> None:
    from data_collectors.fii_dii_collector import collect_fii_dii
    collect_fii_dii()


@asset(
    group_name="nse_daily",
    description="Corporate actions (dividends, splits, bonus, buybacks) and earnings calendar from NSE.",
)
def nse_corporate_actions(context) -> None:
    from data_collectors.nse_actions_collector import collect_nse_actions
    collect_nse_actions()


@asset(
    group_name="nse_daily",
    description="Market news headlines scored by FinBERT (local). Proactive: covers full NSE universe.",
)
def nse_news_sentiment(context) -> None:
    from data_collectors.news_collector import collect_news
    collect_news()


@asset(
    group_name="nse_daily",
    deps=[nse_technical_indicators, nse_fii_dii_flows, nse_corporate_actions, nse_news_sentiment],
    description="BUY/SELL/WATCH signal report. Reads all context data from DB after upstream assets run.",
)
def nse_signals(context) -> None:
    from analysis.generate_signals import generate_daily_report
    generate_daily_report()


# ── NSE Weekly Assets ─────────────────────────────────────────────────────────

@asset(
    group_name="nse_weekly",
    description="Sync full NSE EQ instrument list (~2000 stocks) into stocks table via Kite.",
)
def nse_stock_universe(context) -> None:
    from data_collectors.expand_stock_universe import expand_universe
    result = expand_universe()
    context.log.info(f"Universe expanded — inserted: {result['inserted']}, updated: {result['updated']}, total: {result['total']}")


@asset(
    group_name="nse_weekly",
    description="Fundamentals from Screener.in: P/E, P/B, ROE, ROCE, promoter holding, etc.",
)
def nse_fundamentals(context) -> None:
    from data_collectors.screener_collector import collect_screener_fundamentals
    collect_screener_fundamentals()


@asset(
    group_name="nse_weekly",
    description="RBI macro indicators: repo rate, CPI, WACR, USD/INR from DBIE homepage.",
)
def nse_macro_indicators(context) -> None:
    from data_collectors.rbi_macro_collector import collect_rbi_macro
    collect_rbi_macro()


@asset(
    group_name="nse_weekly",
    description="NSE insider trades (SEBI PIT disclosures) + bulk/block deals, last 7 days.",
)
def nse_insider_trades(context) -> None:
    from data_collectors.insider_bulk_collector import collect_insider_and_bulk
    collect_insider_and_bulk(days=7)


# ── NSE Monthly Assets ────────────────────────────────────────────────────────

@asset(
    group_name="nse_monthly",
    description=(
        "Three-step monthly refresh: "
        "(1) composite 0-100 stock scores from 52W percentile ranks, "
        "(2) FinBERT weight cache purge + re-download, "
        "(3) 52W rolling indicator baselines (mean/std/p10-p90 per stock)."
    ),
)
def nse_model_refresh(context) -> None:
    from jobs.model_refresh import run_model_refresh
    run_model_refresh()


# ── US Market Assets (placeholders) ──────────────────────────────────────────
# Wire a data source (yfinance, Alpaca, Polygon.io) when US coverage is added.
# The EST schedule is already live — just implement these two asset bodies.

@asset(
    group_name="us_daily",
    description="[PLACEHOLDER] US stock OHLCV prices. Wire to yfinance/Alpaca when ready.",
)
def us_raw_prices(context) -> None:
    context.log.info("us_raw_prices: placeholder — no US data source wired yet")


@asset(
    group_name="us_daily",
    deps=[us_raw_prices],
    description="[PLACEHOLDER] US stock signals. Mirrors nse_signals logic for NYSE/NASDAQ.",
)
def us_signals(context) -> None:
    context.log.info("us_signals: placeholder — no US data source wired yet")


# ── Jobs ──────────────────────────────────────────────────────────────────────

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

us_daily_job = define_asset_job(
    name="us_daily_job",
    selection=AssetSelection.groups("us_daily"),
    description="US daily pipeline (placeholder — enable when data source is wired).",
)


# ── Schedules ─────────────────────────────────────────────────────────────────

kite_token_schedule = ScheduleDefinition(
    name="kite_token_daily",
    job=kite_token_job,
    cron_schedule="0 8 * * *",        # 08:00 IST daily
    execution_timezone="Asia/Kolkata",
    description="Refresh Kite access token before NSE market open (09:15 IST).",
)

nse_daily_schedule = ScheduleDefinition(
    name="nse_daily_market",
    job=nse_daily_job,
    cron_schedule="0 16 * * 1-5",     # 16:00 IST Mon-Fri (NSE closes 15:30)
    execution_timezone="Asia/Kolkata",
    description="Post-market NSE pipeline on trading days.",
)

nse_weekly_schedule = ScheduleDefinition(
    name="nse_weekly",
    job=nse_weekly_job,
    cron_schedule="30 7 * * 0",       # 07:30 IST Sunday
    execution_timezone="Asia/Kolkata",
    description="Weekly Sunday batch before Indian market open.",
)

nse_monthly_schedule = ScheduleDefinition(
    name="nse_monthly",
    job=nse_monthly_job,
    cron_schedule="0 2 1 * *",        # 02:00 IST 1st of month
    execution_timezone="Asia/Kolkata",
    description="Monthly model refresh on the 1st of each month.",
)

us_daily_schedule = ScheduleDefinition(
    name="us_daily_market",
    job=us_daily_job,
    cron_schedule="30 16 * * 1-5",    # 16:30 EST Mon-Fri (30 min after NYSE close 16:00)
    execution_timezone="America/New_York",
    description="[PLACEHOLDER] US post-market pipeline. Enable when data source is wired.",
)


# ── Top-level Definitions ─────────────────────────────────────────────────────

defs = Definitions(
    assets=[
        # kite_infra
        kite_token_refreshed,
        # nse_daily
        nse_raw_prices,
        nse_technical_indicators,
        nse_fii_dii_flows,
        nse_corporate_actions,
        nse_news_sentiment,
        nse_signals,
        # nse_weekly
        nse_stock_universe,
        nse_fundamentals,
        nse_macro_indicators,
        nse_insider_trades,
        # nse_monthly
        nse_model_refresh,
        # us_daily
        us_raw_prices,
        us_signals,
    ],
    jobs=[
        kite_token_job,
        nse_daily_job,
        nse_weekly_job,
        nse_monthly_job,
        us_daily_job,
    ],
    schedules=[
        kite_token_schedule,
        nse_daily_schedule,
        nse_weekly_schedule,
        nse_monthly_schedule,
        us_daily_schedule,
    ],
)
