"""
data_collectors/mospi_macro_collector.py

Collects GDP (National Accounts) and WPI (wholesale inflation) from the
official MoSPI MCP server and stores them in macro_indicators.

Source: fastmcp.Client("https://mcp.mospi.gov.in/mcp")
  Tools used: get_data on datasets NAS (GDP) and WPI.

Indicators stored (market='IN', source='mospi_mcp'):
  gdp_constant_price  — real GDP, base 2011-12, INR crore, per quarter
  gdp_current_price   — nominal GDP, INR crore, per quarter
  gdp_growth_yoy      — real GDP YoY growth %, computed from constant_price
  wpi_index           — headline WPI index (base 2011-12), per month
  wpi_inflation       — headline WPI YoY inflation %, computed from index

Each data point is stored with date = the period's representative date
(quarter-end for GDP, month-start for WPI) so a time series accumulates and
re-runs upsert cleanly on the (date, market, indicator) unique key.

Schedule: weekly Sunday 07:30 IST via the nse_macro_indicators Dagster asset.
"""
import os
import sys
import asyncio
import logging
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import get_conn, refresh_log

log = logging.getLogger(__name__)

MOSPI_MCP_URL = "https://mcp.mospi.gov.in/mcp"

# Indian fiscal quarter -> (month, day) of quarter end. FY 2025-26 Q1 = Apr-Jun 2025.
_QUARTER_END = {"Q1": (6, 30), "Q2": (9, 30), "Q3": (12, 31), "Q4": (3, 31)}


def _structured(result) -> dict:
    """Extract the structured JSON payload from a fastmcp CallToolResult."""
    sc = getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)
    return sc or {}


def _quarter_end_date(fy: str, quarter: str) -> date:
    """FY label like '2025-26' + 'Q1' -> date(2025, 6, 30). Q4 falls in the next calendar year."""
    start_year = int(fy.split("-")[0])
    month, day = _QUARTER_END[quarter]
    year = start_year + 1 if quarter == "Q4" else start_year
    return date(year, month, day)


def _month_index(year: int, month_code: int) -> int:
    """Sortable YYYYMM key."""
    return year * 100 + month_code


async def _fetch_gdp(client) -> list[dict]:
    """Quarterly GDP (constant + current price) + computed YoY real growth."""
    res = _structured(await client.call_tool("get_data", {
        "dataset": "NAS",
        "filters": {
            "indicator_code": 5,        # Gross Domestic Product
            "base_year": "2011-12",
            "series": "Current",
            "frequency_code": 2,         # Quarterly
            "limit": 24,
        },
    }))
    records = res.get("data", []) or []
    # Index constant prices by (fy, quarter) to compute YoY growth.
    const_by_q = {}
    for r in records:
        const_by_q[(r["year"], r["quarter"])] = float(r["constant_price"])

    rows = []
    for r in records:
        fy, q = r["year"], r["quarter"]
        d = _quarter_end_date(fy, q)
        period = f"{q} {fy}"
        const_p = float(r["constant_price"])
        curr_p = float(r["current_price"])
        rows.append({"date": d, "indicator": "gdp_constant_price", "value": round(const_p, 2),
                     "unit": "INR_crore", "period": period})
        rows.append({"date": d, "indicator": "gdp_current_price", "value": round(curr_p, 2),
                     "unit": "INR_crore", "period": period})
        prev_fy = f"{int(fy.split('-')[0]) - 1}-{str(int(fy.split('-')[0])).zfill(2)[-2:]}"
        prev = const_by_q.get((prev_fy, q))
        if prev:
            growth = (const_p / prev - 1) * 100
            rows.append({"date": d, "indicator": "gdp_growth_yoy", "value": round(growth, 2),
                         "unit": "pct", "period": period})
    log.info(f"  GDP: {len(records)} quarters fetched, {len(rows)} indicator rows")
    return rows


async def _fetch_wpi(client) -> list[dict]:
    """Headline WPI monthly index + computed YoY inflation %."""
    month_num = {m: i for i, m in enumerate(
        ["January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December"], start=1)}
    records = []
    current_year = date.today().year
    for year in range(current_year - 2, current_year + 1):
        res = _structured(await client.call_tool("get_data", {
            "dataset": "WPI",
            "filters": {
                "base_year": "2011-12",
                "major_group_code": "1000000000",  # headline Wholesale price index
                "year": year,
                "limit": 12,
            },
        }))
        records.extend(res.get("data", []) or [])

    index_by_ym = {}
    for r in records:
        mc = month_num.get(r["month"])
        if mc and r.get("index_value") is not None:
            index_by_ym[_month_index(r["year"], mc)] = float(r["index_value"])

    rows = []
    for r in records:
        mc = month_num.get(r["month"])
        if not mc or r.get("index_value") is None:
            continue
        d = date(r["year"], mc, 1)
        period = f"{r['month'][:3]}-{str(r['year'])[-2:]}"
        idx = float(r["index_value"])
        rows.append({"date": d, "indicator": "wpi_index", "value": round(idx, 2),
                     "unit": "index", "period": period})
        prev = index_by_ym.get(_month_index(r["year"] - 1, mc))
        if prev:
            infl = (idx / prev - 1) * 100
            rows.append({"date": d, "indicator": "wpi_inflation", "value": round(infl, 2),
                         "unit": "pct", "period": period})
    log.info(f"  WPI: {len(records)} months fetched, {len(rows)} indicator rows")
    return rows


async def _collect_async() -> list[dict]:
    from fastmcp import Client
    async with Client(MOSPI_MCP_URL) as client:
        gdp = await _fetch_gdp(client)
        wpi = await _fetch_wpi(client)
    return gdp + wpi


def _store(rows: list[dict]) -> int:
    conn = get_conn()
    cur = conn.cursor()
    upserted = 0
    for row in rows:
        cur.execute(
            """
            INSERT INTO macro_indicators (date, market, indicator, value, unit, period, source)
            VALUES (%s, 'IN', %s, %s, %s, %s, 'mospi_mcp')
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


def collect_mospi_macro() -> dict:
    """Fetch GDP + WPI from MoSPI MCP and upsert into macro_indicators."""
    log.info("=== MoSPI macro (GDP + WPI) collection starting ===")
    with refresh_log("mospi_macro") as meta:
        rows = asyncio.run(_collect_async())
        upserted = _store(rows)
        meta["rows"] = upserted
    indicators = sorted({r["indicator"] for r in rows})
    log.info(f"mospi_macro: {upserted} rows upserted across {indicators}")
    return {"rows_upserted": upserted, "indicators": indicators}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = collect_mospi_macro()
    print(f"Done: {result}")
