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
    description=(
        "Market news headlines scored by FinBERT (local). Proactive, multi-market: "
        "Indian feeds (ET, Moneycontrol, NDTV, Google News IN) + US feeds (Google News US, "
        "CNBC, MarketWatch, Yahoo Finance, Seeking Alpha). Matches against the full NSE + US "
        "stock universe; bare tickers that are common words (COST) or ≤2 chars (V, MA) are not "
        "matched to avoid false positives. Stored in news_sentiment (source='news_sentiment')."
    ),
)
def nse_news_sentiment(context) -> None:
    from data_collectors.news_collector import collect_news
    collect_news()


@asset(
    group_name="nse_daily",
    description=(
        "F&O market-wide data: India VIX, Put/Call Ratio (index/stock/total), "
        "FII index options positioning and futures OI. "
        "Source: NSE participant OI archive CSV + allIndices API."
    ),
)
def nse_fno_data(context) -> None:
    from data_collectors.fno_collector import collect_fno_data
    result = collect_fno_data()
    context.log.info(f"F&O data inserted: {result}")


@asset(
    group_name="nse_daily",
    description=(
        "NSE block deals: large negotiated trades executed in the pre-open block window. "
        "Stored in bulk_deals table with deal_type=block. "
        "Source: NSE snapshot-capital-market-largedeal API."
    ),
)
def nse_block_deals(context) -> None:
    from data_collectors.insider_bulk_collector import collect_block_deals
    stored = collect_block_deals(days=7)
    context.log.info(f"Block deals stored: {stored}")


@asset(
    group_name="nse_daily",
    description=(
        "BSE bulk + block deals via NSE archive CSV (bulk.csv, block.csv) and NSE snapshot API. "
        "BSE direct API (api.bseindia.com) returns HTML for all endpoints — JS-challenge blocked. "
        "Covers dual-listed stocks (NSE+BSE); BSE-exclusive stocks not accessible without browser automation. "
        "Stored in bulk_deals with source=nse_bulk/nse_block."
    ),
)
def bse_bulk_deals(context) -> None:
    from data_collectors.insider_bulk_collector import collect_bulk_deals, collect_block_deals
    n_bulk = collect_bulk_deals(days=7)
    n_block = collect_block_deals(days=7)
    context.log.info(f"BSE/NSE bulk deals: {n_bulk} bulk + {n_block} block stored")


@asset(
    group_name="nse_daily",
    deps=[nse_technical_indicators, nse_fii_dii_flows, nse_corporate_actions, nse_news_sentiment, nse_fno_data, nse_block_deals, bse_bulk_deals],
    description="BUY/SELL/WATCH signal report. Reads all context data from DB after upstream assets run.",
)
def nse_signals(context) -> None:
    from analysis.generate_signals import generate_daily_report
    generate_daily_report()


# ── NSE Weekly Assets ─────────────────────────────────────────────────────────

@asset(
    group_name="nse_weekly",
    description=(
        "Quarterly shareholding pattern from Screener.in: promoter %, FII %, DII %, "
        "government %, public % for all watchlist stocks. Skips if no new quarter available."
    ),
)
def nse_shareholding_pattern(context) -> None:
    from data_collectors.shareholding_collector import collect_shareholding
    result = collect_shareholding()
    context.log.info(
        f"Shareholding: {result['rows_inserted']} new, {result['rows_updated']} updated, "
        f"{result['stocks_checked']} stocks"
    )


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
    description=(
        "India macro indicators in macro_indicators. "
        "RBI DBIE homepage: repo rate, CPI, WACR, USD/INR. "
        "MoSPI MCP (mcp.mospi.gov.in): GDP (level + YoY growth) and WPI (index + YoY inflation). "
        "RBI DBIE via Playwright: forex reserves (weekly) + bank credit/deposit YoY growth (fortnightly)."
    ),
)
def nse_macro_indicators(context) -> None:
    from data_collectors.rbi_macro_collector import collect_rbi_macro
    from data_collectors.mospi_macro_collector import collect_mospi_macro
    from data_collectors.rbi_dbie_collector import collect_rbi_dbie
    collect_rbi_macro()
    mospi = collect_mospi_macro()
    context.log.info(
        f"MoSPI macro: {mospi['rows_upserted']} rows across {mospi['indicators']}"
    )
    dbie = collect_rbi_dbie()
    context.log.info(
        f"RBI DBIE: {dbie['rows_upserted']} rows across {dbie['indicators']}"
    )


@asset(
    group_name="nse_weekly",
    description="NSE insider trades (SEBI PIT disclosures) + bulk/block deals, last 7 days.",
)
def nse_insider_trades(context) -> None:
    from data_collectors.insider_bulk_collector import collect_insider_and_bulk
    collect_insider_and_bulk(days=7)


@asset(
    group_name="nse_weekly",
    description=(
        "Google Search interest (0–100) for each watchlist stock by company name in India. "
        "Stored in macro_indicators as google_trends_{SYMBOL}. "
        "Fetches last 90 days on first run, last 30 days on subsequent runs. "
        "Source: Google Trends via pytrends (geo=IN)."
    ),
)
def google_trends(context) -> None:
    from data_collectors.google_trends_collector import collect_google_trends
    result = collect_google_trends()
    context.log.info(
        f"Google Trends: {result['rows_upserted']} rows, {result['stocks_processed']} stocks"
    )


@asset(
    group_name="nse_weekly",
    description=(
        "F&O expiry calendar from Kite NFO instruments. "
        "Classifies each expiry date as weekly (NIFTY options, every Tuesday near-term), "
        "monthly (all stocks + FUT + options, end of each month), "
        "or quarterly (long-dated index options, quarter-end). "
        "18 rows — refreshed weekly as new contracts are listed."
    ),
)
def nse_expiry_calendar(context) -> None:
    from data_collectors.expiry_calendar_collector import collect_expiry_calendar
    result = collect_expiry_calendar()
    context.log.info(
        f"Expiry calendar: {result['rows_upserted']} rows "
        f"({result['weekly']} weekly, {result['monthly']} monthly, {result['quarterly']} quarterly)"
    )


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
    description=(
        "US insider transactions from SEC EDGAR Form 4 filings (last 30 days) for the "
        "seeded US universe. Parses non-derivative buys/sells into insider_trades "
        "(source='sec_form4'). Free; needs a contact-email User-Agent per SEC policy."
    ),
)
def us_insider_trades(context) -> None:
    from data_collectors.sec_form4_collector import collect_sec_form4
    result = collect_sec_form4()
    context.log.info(
        f"SEC Form 4: {result['rows_upserted']} new txns across {result['stocks_with_data']} stocks"
    )


@asset(
    group_name="us_daily",
    deps=[us_raw_prices],
    description="[PLACEHOLDER] US stock signals. Mirrors nse_signals logic for NYSE/NASDAQ.",
)
def us_signals(context) -> None:
    context.log.info("us_signals: placeholder — no US data source wired yet")


# ── US Weekly Assets ──────────────────────────────────────────────────────────

@asset(
    group_name="us_weekly",
    description=(
        "US macro indicators in macro_indicators (market='US', source='fred'). "
        "FRED keyless fredgraph.csv endpoint via curl: Fed funds rate (FEDFUNDS), "
        "CPI index + YoY inflation (CPIAUCSL), unemployment rate (UNRATE), "
        "real GDP level + YoY growth (GDPC1)."
    ),
)
def us_macro(context) -> None:
    from data_collectors.fred_macro_collector import collect_fred_macro
    result = collect_fred_macro()
    context.log.info(
        f"FRED macro: {result['rows_upserted']} rows across {result['indicators']}"
    )


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
    description="US daily pipeline (placeholder — enable when data source is wired).",
)

us_weekly_job = define_asset_job(
    name="us_weekly_job",
    selection=AssetSelection.groups("us_weekly"),
    description="US weekly batch: FRED macro indicators (Fed rate, CPI, GDP, unemployment).",
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

nse_fno_schedule = ScheduleDefinition(
    name="nse_fno_daily",
    job=nse_fno_job,
    cron_schedule="45 16 * * 1-5",    # 16:45 IST Mon-Fri (NSE participant OI CSV published ~16:30)
    execution_timezone="Asia/Kolkata",
    description="Daily F&O data: India VIX + PCR (index/FII/total) from NSE archives.",
)

bse_bulk_schedule = ScheduleDefinition(
    name="bse_bulk_daily",
    job=bse_bulk_job,
    cron_schedule="30 16 * * 1-5",    # 16:30 IST Mon-Fri (after NSE closes 15:30)
    execution_timezone="Asia/Kolkata",
    description="Daily bulk + block deal collection. BSE API is JS-blocked; uses NSE archive CSV fallback.",
)

us_daily_schedule = ScheduleDefinition(
    name="us_daily_market",
    job=us_daily_job,
    cron_schedule="30 16 * * 1-5",    # 16:30 EST Mon-Fri (30 min after NYSE close 16:00)
    execution_timezone="America/New_York",
    description="[PLACEHOLDER] US post-market pipeline. Enable when data source is wired.",
)

us_weekly_schedule = ScheduleDefinition(
    name="us_weekly",
    job=us_weekly_job,
    cron_schedule="0 7 * * 0",        # 07:00 EST Sunday
    execution_timezone="America/New_York",
    description="Weekly US macro refresh from FRED (Fed rate, CPI, GDP, unemployment).",
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
        nse_fno_data,
        nse_block_deals,
        bse_bulk_deals,
        nse_signals,
        # nse_weekly
        nse_shareholding_pattern,
        nse_stock_universe,
        nse_fundamentals,
        nse_macro_indicators,
        nse_insider_trades,
        google_trends,
        nse_expiry_calendar,
        # nse_monthly
        nse_model_refresh,
        # us_daily
        us_raw_prices,
        us_insider_trades,
        us_signals,
        # us_weekly
        us_macro,
    ],
    jobs=[
        kite_token_job,
        nse_daily_job,
        nse_fno_job,
        bse_bulk_job,
        nse_weekly_job,
        nse_monthly_job,
        us_daily_job,
        us_weekly_job,
    ],
    schedules=[
        kite_token_schedule,
        nse_daily_schedule,
        nse_fno_schedule,
        bse_bulk_schedule,
        nse_weekly_schedule,
        nse_monthly_schedule,
        us_daily_schedule,
        us_weekly_schedule,
    ],
)
