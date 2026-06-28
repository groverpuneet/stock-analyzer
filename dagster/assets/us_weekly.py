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
