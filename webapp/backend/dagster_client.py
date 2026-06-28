"""Minimal Dagster GraphQL client — launch single-asset materializations and poll runs.

The Dagster webserver exposes a GraphQL API at http://localhost:3000/graphql.
We use the implicit __ASSET_JOB with an assetSelection of one key, so triggering
a source materializes exactly that asset (no upstream re-runs).
"""
import os
import json
import urllib.request

DAGSTER_GRAPHQL = os.environ.get("DAGSTER_GRAPHQL_URL", "http://localhost:3000/graphql")
REPO_NAME = "__repository__"
REPO_LOCATION = "stock_analyzer"

_LAUNCH = """
mutation Launch($asset: String!) {
  launchPipelineExecution(executionParams: {
    selector: {
      repositoryLocationName: "stock_analyzer",
      repositoryName: "__repository__",
      pipelineName: "__ASSET_JOB",
      assetSelection: [{ path: [$asset] }]
    },
    mode: "default"
  }) {
    __typename
    ... on LaunchRunSuccess { run { runId status } }
    ... on PythonError { message }
    ... on InvalidSubsetError { message }
    ... on PipelineNotFoundError { message }
    ... on RunConfigValidationInvalid { errors { message } }
    ... on PresetNotFoundError { message }
    ... on ConflictingExecutionParamsError { message }
  }
}
"""

_RUN_STATUS = """
query RunStatus($runId: ID!) {
  runOrError(runId: $runId) {
    __typename
    ... on Run { runId status startTime endTime }
    ... on RunNotFoundError { message }
    ... on PythonError { message }
  }
}
"""


def _post(query: str, variables: dict, timeout: float = 10) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        DAGSTER_GRAPHQL, data=body, headers={"content-type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def launch_asset(asset: str) -> dict:
    """Launch a materialization for one asset. Returns {ok, run_id?, error?}."""
    try:
        data = _post(_LAUNCH, {"asset": asset})
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"Dagster unreachable: {e}"}
    node = (data.get("data") or {}).get("launchPipelineExecution") or {}
    if node.get("__typename") == "LaunchRunSuccess":
        return {"ok": True, "run_id": node["run"]["runId"], "status": node["run"]["status"]}
    msg = node.get("message") or json.dumps(data.get("errors") or node)
    return {"ok": False, "error": f"{node.get('__typename', 'Error')}: {msg}"}


def run_status(run_id: str) -> dict:
    try:
        data = _post(_RUN_STATUS, {"runId": run_id})
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"Dagster unreachable: {e}"}
    node = (data.get("data") or {}).get("runOrError") or {}
    if node.get("__typename") == "Run":
        return {"ok": True, "status": node["status"]}
    return {"ok": False, "error": node.get("message", "unknown")}


def healthy() -> bool:
    try:
        _post("{ __typename }", {}, timeout=4)
        return True
    except Exception:  # noqa: BLE001
        return False
