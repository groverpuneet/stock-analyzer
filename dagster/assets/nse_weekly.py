"""nse_weekly group — Sunday 07:30 IST batch."""
from dagster import asset


@asset(
    group_name="nse_weekly",
    description="Sync full NSE EQ instrument list (~2000 stocks) into stocks table via Kite.",
)
def nse_stock_universe(context) -> None:
    from data_collectors.expand_stock_universe import expand_universe
    result = expand_universe()
    context.log.info(
        f"Universe expanded — inserted: {result['inserted']}, updated: {result['updated']}, total: {result['total']}"
    )


@asset(
    group_name="nse_weekly",
    description=(
        "Fundamentals from Screener.in: P/E, P/B, ROE, ROCE, promoter holding, etc. "
        "Also refreshes ~10yr monthly P/E history (Screener chart API) into fundamentals "
        "and recomputes stock_scores.pe_percentile (current P/E vs the stock's own 5yr range)."
    ),
)
def nse_fundamentals(context) -> None:
    from data_collectors.screener_collector import collect_screener_fundamentals
    from data_collectors.screener_pe_history_collector import seed_pe_history
    collect_screener_fundamentals()
    pe = seed_pe_history()
    context.log.info(
        f"PE history: {pe['rows_upserted']} rows across {pe['stocks_filled']} stocks, "
        f"{pe['pe_percentiles_set']} percentiles set"
    )


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
    context.log.info(f"MoSPI macro: {mospi['rows_upserted']} rows across {mospi['indicators']}")
    dbie = collect_rbi_dbie()
    context.log.info(f"RBI DBIE: {dbie['rows_upserted']} rows across {dbie['indicators']}")


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


@asset(
    group_name="nse_weekly",
    description=(
        "Google Search interest (0–100) for each watchlist stock by company name in India. "
        "Stored in macro_indicators as google_trends_{SYMBOL}. "
        "Fetches last 90 days on first run, last 30 days on subsequent runs. "
        "Source: Google Trends via pytrends (geo=IN)."
    ),
)
def nse_google_trends(context) -> None:
    from data_collectors.google_trends_collector import collect_google_trends
    result = collect_google_trends()
    context.log.info(
        f"Google Trends: {result['rows_upserted']} rows, {result['stocks_processed']} stocks"
    )


@asset(
    group_name="nse_weekly",
    deps=[nse_fundamentals, nse_shareholding_pattern],
    description=(
        "Post-run audit: after the weekly pipeline, detect fundamentals/shareholding coverage "
        "gaps into data_quality_log, update per-stock data_completeness_score, and note any "
        "stock below 80% in STATUS.md. Runs last in nse_weekly_job."
    ),
)
def nse_weekly_audit(context) -> None:
    from utils.data_quality import run_audit
    summary = run_audit("nse_weekly")
    context.log.info(f"Weekly audit: {summary['gaps']} gaps; "
                     f"{len(summary['completeness']['below_80'])} stocks <80% complete")
