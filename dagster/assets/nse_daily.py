"""nse_daily group — post-market NSE pipeline (Mon-Fri 16:00 IST)."""
from dagster import asset


@asset(
    group_name="nse_daily",
    deps=["kite_token_refreshed"],   # prices need a fresh Kite token (refreshed 08:00 IST)
    description=(
        "OHLCV daily prices + live quotes for watchlist stocks via Kite Connect. "
        "Guards on token validity — if the Kite token is missing/expired the NSE pipeline "
        "is skipped for the day (logged) rather than crashing downstream assets."
    ),
)
def nse_raw_prices(context) -> None:
    import os
    from data_collectors.collect_watchlist_data import collect_data, get_kite_client
    # Token guard: a cheap validity probe. If it fails, skip the day's NSE pipeline.
    try:
        kite = get_kite_client()
        kite.ltp(["NSE:RELIANCE"])   # lightweight read-only call
    except Exception as e:  # noqa: BLE001
        context.log.error(f"Kite token invalid — skipping NSE prices today: {e}")
        return
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
    description=(
        "4-pillar explainable signals (technical / fundamental / flow / external) per "
        "watchlist stock, across SHORT/MID/LONG horizons, into signal_explanations. "
        "External sentiment (DDG + Google-News + VADER) is fetched fresh and cached 6h. "
        "Runs after news_sentiment so internal + external sentiment are both current."
    ),
)
def nse_signals(context) -> None:
    from signals.engine import run_signals
    summary = run_signals(external_pause=1.2)
    context.log.info(
        f"Signals: {summary['stocks']} stocks · external fetched {summary['external_fetched']} · "
        f"avg pillar scores {summary['avg_pillar_scores']}"
    )


@asset(
    group_name="nse_daily",
    deps=[nse_signals],
    description=(
        "Post-run audit: after the daily pipeline, detect coverage gaps (ohlcv/indicators/"
        "signals/news) into data_quality_log, update per-stock data_completeness_score, and "
        "note any stock below 80% in STATUS.md. Runs last in nse_daily_job."
    ),
)
def nse_daily_audit(context) -> None:
    from utils.data_quality import run_audit
    summary = run_audit("nse_daily")
    context.log.info(f"Daily audit: {summary['gaps']} gaps; "
                     f"{len(summary['completeness']['below_80'])} stocks <80% complete")


@asset(
    group_name="nse_daily",
    deps=[nse_signals],
    description=(
        "India Fear & Greed Index (0-100) computed after the daily pipeline from VIX, "
        "Put/Call ratio, FII flows, % watchlist above SMA50, % RSI>50, avg news sentiment. "
        "Stored in macro_indicators (indicator='india_fear_greed_index')."
    ),
)
def india_fear_greed(context) -> None:
    from data_collectors.fear_greed_collector import compute_india_fear_greed
    from utils.db import refresh_log
    # Record the run so the "computed" timestamp on the dashboard widget is accurate
    # even when this asset is materialized on its own (e.g. the 🔄 button).
    with refresh_log("fear_greed") as meta:
        r = compute_india_fear_greed()
        meta["rows"] = 1
    context.log.info(f"India F&G: {r['score']} ({r['rating']})")
