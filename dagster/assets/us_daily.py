"""us_daily group — US post-market pipeline (Mon-Fri 16:30 EST)."""
from dagster import asset


@asset(
    group_name="us_daily",
    description=(
        "US daily OHLCV for the seeded US universe via Polygon.io Aggregates API "
        "(free tier: 5 calls/min, EOD, ~2yr history). Stored in daily_prices "
        "(market via stocks join). Incremental daily run pulls the last 7 days; "
        "the full 2yr backfill is a one-time manual collect_us_prices() call."
    ),
)
def us_raw_prices(context) -> None:
    from data_collectors.polygon_prices_collector import collect_us_prices
    result = collect_us_prices(lookback_days=7)
    context.log.info(
        f"US prices: {result['rows_upserted']} bars across {result['stocks_with_data']} stocks"
    )


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
    context.log.info("us_signals: placeholder — no US signal logic wired yet")


@asset(
    group_name="us_daily",
    description=(
        "US Fear & Greed Index from CNN's free dataviz API, stored in macro_indicators "
        "(indicator='us_fear_greed_index') with ~40 days of history for the chart."
    ),
)
def us_fear_greed(context) -> None:
    from data_collectors.fear_greed_collector import collect_us_fear_greed
    r = collect_us_fear_greed()
    context.log.info(f"US F&G: {r['score']} ({r['rating']})")
