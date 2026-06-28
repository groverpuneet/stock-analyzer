"""nse_monthly group — 1st of month 02:00 IST."""
import os
from dagster import asset


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
    # The project-root `jobs/` package is shadowed on the bare name by dagster/jobs.py
    # (dagster dir is first on sys.path), so load jobs/model_refresh.py by explicit path.
    import importlib.util
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(root, "jobs", "model_refresh.py")
    spec = importlib.util.spec_from_file_location("sa_model_refresh", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.run_model_refresh()


@asset(
    group_name="nse_monthly",
    description=(
        "MF (DII) ownership per stock from shareholding_pattern. Uses quarterly DII% "
        "as proxy for MF ownership since detailed AMFI portfolio data requires login. "
        "Tracks DII changes over time in mf_stock_holdings table."
    ),
)
def nse_mf_holdings(context) -> None:
    from data_collectors.mf_holdings_collector import collect_mf_holdings
    collect_mf_holdings(months=24)
