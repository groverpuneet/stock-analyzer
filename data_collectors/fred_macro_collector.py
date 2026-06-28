"""
data_collectors/fred_macro_collector.py

Collects US macro indicators from FRED (Federal Reserve Economic Data) and
stores them in macro_indicators with market='US', source='fred'.

Source: the keyless `fredgraph.csv` download endpoint
  https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES>&cosd=<start>
  Unlike the JSON API, this CSV endpoint needs no API key.

Series collected:
  FEDFUNDS  — Effective Federal Funds Rate, monthly, %      -> fed_funds_rate
  CPIAUCSL  — CPI All Urban Consumers, monthly, index 1982-84=100
                                                            -> cpi_index
                                          + computed YoY    -> cpi_inflation_yoy
  UNRATE    — Civilian Unemployment Rate, monthly, %        -> unemployment_rate
  GDPC1     — Real GDP, quarterly, billions chained 2017 $  -> gdp_real
                                          + computed YoY    -> gdp_growth_yoy

Each observation is stored with date = FRED observation_date so a time series
accumulates and re-runs upsert cleanly on (date, market, indicator).

Schedule: weekly via the us_macro Dagster asset.
"""
import os
import sys
import csv
import io
import shutil
import logging
import subprocess
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import get_conn, refresh_log

log = logging.getLogger(__name__)

FREDGRAPH_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
# ~4 years of history — enough for YoY computation plus a usable trend.
_COSD = f"{date.today().year - 4}-01-01"

# series_id -> (indicator name, unit, yoy_indicator or None, yoy_lag_periods)
# yoy_lag_periods: 12 for monthly series, 4 for quarterly — index back to same period prior year.
SERIES = {
    "FEDFUNDS": ("fed_funds_rate",    "pct",   None,                 None),
    "CPIAUCSL": ("cpi_index",         "index", "cpi_inflation_yoy",  12),
    "UNRATE":   ("unemployment_rate", "pct",   None,                 None),
    "GDPC1":    ("gdp_real",          "USD_billion", "gdp_growth_yoy", 4),
}


def _period_label(d: date, quarterly: bool) -> str:
    if quarterly:
        return f"{d.year}-Q{(d.month - 1) // 3 + 1}"
    return f"{d.year}-{d.month:02d}"


def _fetch_csv(series_id: str) -> str:
    """Download a FRED series CSV.

    FRED sits behind Akamai, which drops Python's TLS ClientHello (the requests/
    urllib handshake gets a RemoteDisconnected). curl's TLS fingerprint is accepted,
    and curl ships in both the host venv environment and the Dagster container image,
    so we shell out to it rather than carry a fragile in-process HTTP client.

    Note: Akamai tarpits a custom User-Agent on this endpoint (connection hangs with
    0 bytes). curl's default UA is accepted, so we deliberately do NOT override it.
    """
    if not shutil.which("curl"):
        raise RuntimeError("curl not found on PATH — required to fetch FRED (Akamai blocks Python TLS)")
    url = f"{FREDGRAPH_CSV}?id={series_id}&cosd={_COSD}"
    proc = subprocess.run(
        ["curl", "-sS", "--fail", "--http1.1", "--retry", "2", "--max-time", "40", url],
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"curl failed for {series_id} (exit {proc.returncode}): {proc.stderr.strip()[:200]}")
    return proc.stdout


def _fetch_series(series_id: str) -> list[tuple]:
    """Return [(date, float_value), ...] for a FRED series, skipping missing '.' points."""
    out = []
    reader = csv.reader(io.StringIO(_fetch_csv(series_id)))
    rows = list(reader)
    if not rows:
        return out
    # Header is "observation_date,<SERIES_ID>" (older exports use "DATE").
    for r in rows[1:]:
        if len(r) < 2:
            continue
        raw_date, raw_val = r[0].strip(), r[1].strip()
        if not raw_date or raw_val in ("", "."):
            continue
        try:
            y, m, d = (int(x) for x in raw_date.split("-"))
            out.append((date(y, m, d), float(raw_val)))
        except (ValueError, TypeError):
            continue
    return out


def _build_rows() -> list[dict]:
    rows = []
    for series_id, (indicator, unit, yoy_ind, yoy_lag) in SERIES.items():
        points = _fetch_series(series_id)
        quarterly = yoy_lag == 4
        log.info(f"  {series_id}: {len(points)} observations")
        for idx, (d, val) in enumerate(points):
            period = _period_label(d, quarterly)
            rows.append({"date": d, "indicator": indicator, "value": round(val, 4),
                         "unit": unit, "period": period})
            if yoy_ind and idx >= yoy_lag:
                prev = points[idx - yoy_lag][1]
                if prev:
                    yoy = (val / prev - 1) * 100
                    rows.append({"date": d, "indicator": yoy_ind, "value": round(yoy, 2),
                                 "unit": "pct", "period": period})
    return rows


def _store(rows: list[dict]) -> int:
    conn = get_conn()
    cur = conn.cursor()
    upserted = 0
    for row in rows:
        cur.execute(
            """
            INSERT INTO macro_indicators (date, market, indicator, value, unit, period, source)
            VALUES (%s, 'US', %s, %s, %s, %s, 'fred')
            ON CONFLICT (date, market, indicator) DO UPDATE SET
                value = EXCLUDED.value, unit = EXCLUDED.unit,
                period = EXCLUDED.period, source = EXCLUDED.source
            """,
            (row["date"], row["indicator"], row["value"], row["unit"], row["period"]),
        )
        upserted += 1
    conn.commit()
    cur.close()
    conn.close()
    return upserted


def collect_fred_macro() -> dict:
    """Fetch US macro series from FRED and upsert into macro_indicators."""
    log.info("=== FRED US macro collection starting ===")
    with refresh_log("fred_macro") as meta:
        rows = _build_rows()
        upserted = _store(rows)
        meta["rows"] = upserted
    indicators = sorted({r["indicator"] for r in rows})
    log.info(f"fred_macro: {upserted} rows upserted across {indicators}")
    return {"rows_upserted": upserted, "indicators": indicators}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = collect_fred_macro()
    print(f"Done: {result}")
