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


@asset(
    group_name="maintenance",
    description=(
        "Targeted gap fill: re-run only what's missing for the affected stocks (not full "
        "jobs) for open data_quality_log gaps, then re-detect to resolve fixed ones and "
        "refresh completeness scores. Triggered by data_quality_sensor every 30 min."
    ),
)
def nse_gap_fill(context) -> None:
    from utils.data_quality import unresolved_gaps, fill_gaps
    gaps = unresolved_gaps(older_than_minutes=60)
    if not gaps:
        context.log.info("No unresolved gaps older than 1h.")
        return
    context.log.info(f"Filling {len(gaps)} unresolved gap(s)…")
    result = fill_gaps(gaps)
    context.log.info(f"Gap fill: {result['filled']}")
