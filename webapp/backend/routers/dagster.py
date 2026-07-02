"""Generic Dagster materialization API.

POST /api/dagster/materialize  {"asset": "nse_fii_dii_flows"}  -> launch one asset
                               {"job":   "nse_daily_job"}      -> launch a full job
GET  /api/dagster/run-status/{run_id}  -> QUEUED / STARTED / SUCCESS / FAILURE ...

Thin wrapper over dagster_client so every "🔄 Refresh" button in the UI has one
uniform way to trigger work and poll it.
"""
from fastapi import APIRouter
from pydantic import BaseModel

import dagster_client

router = APIRouter(prefix="/api/dagster", tags=["dagster"])


class MaterializeReq(BaseModel):
    asset: str | None = None
    job: str | None = None


@router.post("/materialize")
def materialize(req: MaterializeReq):
    """Launch a single asset (assetSelection) or a full job. Returns {ok, run_id}."""
    if req.asset:
        res = dagster_client.launch_asset(req.asset)
        res["asset"] = req.asset
        return res
    if req.job:
        res = dagster_client.launch_job(req.job)
        res["job"] = req.job
        return res
    return {"ok": False, "error": "provide 'asset' or 'job'"}


@router.get("/run-status/{run_id}")
def run_status(run_id: str):
    """Current run status for polling (frontend polls every 3s while running)."""
    return dagster_client.run_status(run_id)


@router.get("/healthy")
def healthy():
    return {"healthy": dagster_client.healthy()}
