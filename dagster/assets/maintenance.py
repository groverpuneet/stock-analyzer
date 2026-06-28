"""maintenance group — queue-driven indicator recompute (safety net)."""
from dagster import asset


@asset(
    group_name="maintenance",
    description=(
        "Drain recompute_queue: recompute technical indicators for stocks whose "
        "daily_prices changed (queued by an AFTER INSERT trigger), then clear those "
        "rows. Triggered by indicator_recompute_sensor every 5 min — the safety net "
        "for prices that land outside the normal daily job (manual backfills, scripts)."
    ),
)
def nse_indicator_recompute(context) -> None:
    from analysis.calculate_indicators import recompute_queued_indicators
    result = recompute_queued_indicators()
    context.log.info(
        f"Indicator recompute: {result['recomputed']}/{result['queued']} queued stocks"
    )
