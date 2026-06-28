"""nse_daily group — post-market NSE pipeline (Mon-Fri 16:00 IST)."""
from dagster import asset


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
    deps=[nse_technical_indicators, nse_fii_dii_flows, nse_corporate_actions,
          nse_news_sentiment, nse_fno_data, nse_block_deals, bse_bulk_deals],
    description="BUY/SELL/WATCH signal report. Reads all context data from DB after upstream assets run.",
)
def nse_signals(context) -> None:
    from analysis.generate_signals import generate_daily_report
    generate_daily_report()
