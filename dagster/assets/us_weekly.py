"""us_weekly group — US macro batch (Sunday 07:00 EST)."""
from dagster import asset


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


@asset(
    group_name="us_weekly",
    description=(
        "SEC 13F-HR institutional holdings for top 20 hedge funds, activist investors, "
        "and value managers. Tracks quarterly portfolio changes for Berkshire, Bridgewater, "
        "Renaissance, Citadel, Pershing Square, etc."
    ),
)
def us_13f_holdings(context) -> None:
    from data_collectors.sec_13f_collector import collect_13f_holdings
    collect_13f_holdings(quarters=2)
