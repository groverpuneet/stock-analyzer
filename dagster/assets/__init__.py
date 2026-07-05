"""Dagster asset definitions, split by group.

Path bootstrap: put the dagster/ dir first (so sibling modules — jobs, schedules,
sensors, assets.* — import by bare name) and the project root second (so the
collector packages data_collectors/analysis/utils resolve). The local
dagster/ dir shadows the project-root jobs/ package on the bare name `jobs`;
nse_monthly loads jobs/model_refresh.py by explicit file path to avoid that.
"""
import os
import sys

_DAG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../stock-analyzer/dagster
_ROOT = os.path.dirname(_DAG_DIR)                                        # .../stock-analyzer
for _p in (_ROOT, _DAG_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)
