"""
data_collectors/rbi_dbie_collector.py

Collects RBI macro data from the DBIE portal (data.rbi.org.in) via Playwright
and stores it in macro_indicators.

Two datasets:
  1. Foreign Exchange Reserves — weekly, from the dbie_foreignExchangeReserves
     gateway service. Components: Total Reserves, Foreign Currency Assets, Gold,
     SDR, Reserve position in the IMF. Stored in USD billion.
  2. Bank credit / deposit growth — fortnightly, parsed from the official
     "Macro-economic Indicators" Excel file (Fortnightly sheet). YoY growth is
     computed from the outstanding ₹-crore series.

Why Playwright (not requests): data.rbi.org.in serves TLS that Mac LibreSSL
rejects, and the DBIE gateway requires a per-session token. We launch a real
Chromium with ignore_https_errors=True, let the SPA mint its session token
(stored in sessionStorage as 'sessionId'), then replay the gateway calls with
that token as the 'authorization' header — which returns clean JSON / a clean
XLSX (browser response interception corrupts the binary, so we replay instead).

Indicators stored (market='IN', source='rbi_dbie'):
  forex_reserves_total / _fca / _gold / _sdr / _imf   (USD_billion)
  bank_credit_outstanding                              (INR_crore)
  bank_credit_growth_yoy / non_food_credit_growth_yoy
  aggregate_deposits_growth_yoy                        (pct)
  credit_deposit_ratio                                 (pct)

Schedule: weekly Sunday 07:30 IST via the nse_macro_indicators Dagster asset.
"""
import os
import sys
import json
import html
import logging
import warnings
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import get_conn, refresh_log

warnings.filterwarnings("ignore", module="openpyxl")
log = logging.getLogger(__name__)

DBIE_HOME = "https://data.rbi.org.in/DBIE/#/dbie/home"
GATEWAY = "https://data.rbi.org.in/CIMS_Gateway_DBIE/GATEWAY/SERVICES/"

# reserveCode -> indicator name (component of forex reserves)
_FOREX_COMPONENTS = {
    "TR": "forex_reserves_total",
    "FCA": "forex_reserves_fca",
    "GOLD": "forex_reserves_gold",
    "SDR": "forex_reserves_sdr",
    "IMF": "forex_reserves_imf",
}


def _decode(resp_text: str) -> dict:
    """DBIE gateway returns HTML-entity-encoded JSON."""
    return json.loads(html.unescape(resp_text))


def _get_session_token(page) -> str:
    """The SPA stores its gateway session token in sessionStorage['sessionId']."""
    for _ in range(20):
        sid = page.evaluate("() => sessionStorage.getItem('sessionId')")
        if sid:
            return sid
        page.wait_for_timeout(1000)
    raise RuntimeError("DBIE session token never appeared in sessionStorage")


def _auth_headers(token: str) -> dict:
    return {
        "authorization": token,
        "channelkey": "key2",
        "datatype": "application/json",
        "content-type": "application/json",
    }


def _fetch_forex(ctx, token: str) -> list[dict]:
    """Latest weekly value for each reserve component (+ 12-week series for total)."""
    today = date.today()
    payload_dates = {
        "fromDate": (today - timedelta(days=400)).strftime("%Y-%m-%d 00:00:00"),
        "toDate": today.strftime("%Y-%m-%d 00:00:00"),
        "frequency": "Weekly",
    }
    rows = []
    for code, indicator in _FOREX_COMPONENTS.items():
        r = ctx.request.post(
            GATEWAY + "dbie_foreignExchangeReserves",
            headers=_auth_headers(token),
            data={"body": {"currencyCode": "USD", "reserveCode": code, **payload_dates}},
        )
        result = _decode(r.text()).get("body", {}).get("resultList", [])
        points = []
        for item in result:
            amt = item.get("amount")
            ts = item.get("timeDate")
            if amt is None or ts is None:
                continue
            d = datetime.utcfromtimestamp(ts / 1000).date()
            points.append((d, float(amt) / 1e9))  # USD -> USD billion
        points.sort()
        if not points:
            log.warning(f"  forex {code}: no data")
            continue
        # Total reserves: keep last 12 weeks as a trend. Components: latest only.
        keep = points[-12:] if code == "TR" else points[-1:]
        for d, val in keep:
            rows.append({"date": d, "indicator": indicator, "value": round(val, 3),
                         "unit": "USD_billion", "period": d.strftime("%d-%b-%y")})
    log.info(f"  Forex: {len(rows)} rows across {len(_FOREX_COMPONENTS)} components")
    return rows


def _fetch_credit(ctx, token: str) -> list[dict]:
    """Bank credit / deposit YoY growth from the official Macro-economic Indicators XLSX."""
    import io
    import openpyxl

    r = ctx.request.post(
        GATEWAY + "download/dbie_FileDownloadHDFSAction",
        headers={"authorization": token, "channelkey": "key2"},
        multipart={"requestMessage": json.dumps({"body": {"Filename": "MacroeconomicIndicators"}})},
    )
    wb = openpyxl.load_workbook(io.BytesIO(r.body()), read_only=True, data_only=True)
    ws = wb["Fortnightly"]
    sheet_rows = list(ws.iter_rows(values_only=True))
    hdr_idx = next(i for i, row in enumerate(sheet_rows)
                   if row and any("Bank Credit" in str(c) for c in row if c))
    # Columns (1-based observed): 1 Period, 2 Non-Food Credit, 4 Aggregate Deposits,
    # 5 Bank Credit, 10 Credit-Deposit Ratio.
    COL = {"period": 1, "non_food": 2, "agg_dep": 4, "bank_credit": 5, "cd_ratio": 10}

    def _num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    series = []
    for row in sheet_rows[hdr_idx + 1:]:
        if not row or row[COL["period"]] is None:
            continue
        d = row[COL["period"]]
        d = d.date() if isinstance(d, datetime) else d
        series.append({
            "date": d,
            "bank_credit": _num(row[COL["bank_credit"]]),
            "non_food": _num(row[COL["non_food"]]),
            "agg_dep": _num(row[COL["agg_dep"]]),
            "cd_ratio": _num(row[COL["cd_ratio"]]),
        })

    valid = [s for s in series if s["bank_credit"] is not None]
    if not valid:
        log.warning("  Credit: no valid Bank Credit rows in XLSX")
        return []
    latest = max(valid, key=lambda s: s["date"])
    target = latest["date"] - timedelta(days=365)
    yago = min(valid, key=lambda s: abs((s["date"] - target).days))

    period = latest["date"].strftime("%d-%b-%y")
    rows = [{
        "date": latest["date"], "indicator": "bank_credit_outstanding",
        "value": round(latest["bank_credit"], 2), "unit": "INR_crore", "period": period,
    }]
    if latest["cd_ratio"] is not None:
        rows.append({"date": latest["date"], "indicator": "credit_deposit_ratio",
                     "value": round(latest["cd_ratio"], 2), "unit": "pct", "period": period})
    for key, indicator in [("bank_credit", "bank_credit_growth_yoy"),
                           ("non_food", "non_food_credit_growth_yoy"),
                           ("agg_dep", "aggregate_deposits_growth_yoy")]:
        if latest[key] and yago.get(key):
            growth = (latest[key] / yago[key] - 1) * 100
            rows.append({"date": latest["date"], "indicator": indicator,
                         "value": round(growth, 2), "unit": "pct", "period": period})
    log.info(f"  Credit: latest fortnight {latest['date']}, YoY base {yago['date']}, {len(rows)} rows")
    return rows


def _store(rows: list[dict]) -> int:
    if not rows:
        return 0
    conn = get_conn()
    cur = conn.cursor()
    upserted = 0
    for row in rows:
        cur.execute(
            """
            INSERT INTO macro_indicators (date, market, indicator, value, unit, period, source)
            VALUES (%s, 'IN', %s, %s, %s, %s, 'rbi_dbie')
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


def collect_rbi_dbie() -> dict:
    """Fetch forex reserves + bank credit/deposit growth from RBI DBIE and upsert."""
    from playwright.sync_api import sync_playwright

    log.info("=== RBI DBIE (forex reserves + credit growth) collection starting ===")
    all_rows = []
    with refresh_log("rbi_dbie") as meta:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(ignore_https_errors=True)
            page = ctx.new_page()
            page.goto(DBIE_HOME, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
            token = _get_session_token(page)
            log.info(f"  DBIE session token acquired ({token[:6]}...)")
            for label, fn in [("forex", _fetch_forex), ("credit", _fetch_credit)]:
                try:
                    all_rows.extend(fn(ctx, token))
                except Exception as e:
                    log.error(f"  {label} fetch failed: {e}", exc_info=True)
            browser.close()
        upserted = _store(all_rows)
        meta["rows"] = upserted
    indicators = sorted({r["indicator"] for r in all_rows})
    log.info(f"rbi_dbie: {upserted} rows upserted across {indicators}")
    return {"rows_upserted": upserted, "indicators": indicators}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = collect_rbi_dbie()
    print(f"Done: {result}")
