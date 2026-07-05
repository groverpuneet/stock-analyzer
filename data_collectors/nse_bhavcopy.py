"""
data_collectors/nse_bhavcopy.py

Free, non-brokerage NSE market-data fetchers — the Kite replacement.

Pulls NSE's public UDiFF bhavcopy archives (static ZIPs, no auth, no JS
challenge — only a browser User-Agent is required):

  - Cash market (equities) EOD OHLCV + symbol master:
      https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{YYYYMMDD}_F_0000.csv.zip
  - F&O (derivatives) contract EOD (expiry calendar source):
      https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{YYYYMMDD}_F_0000.csv.zip

NOTE: jugaad-data's bhavcopy_fo_raw() is broken (points at the pre-2024 URL
NSE discontinued), so we fetch the UDiFF archives directly.

UDiFF columns used:
  CM: TradDt, TckrSymb, ISIN, SctySrs, OpnPric, HghPric, LwPric, ClsPric, LastPric, TtlTradgVol
  FO: TckrSymb, FinInstrmTp, XpryDt, OptnTp, ISIN
"""
import csv
import io
import zipfile
from datetime import date, timedelta

import requests

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/134.0 Safari/537.36"
)
_CM_URL = "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{ymd}_F_0000.csv.zip"
_FO_URL = "https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{ymd}_F_0000.csv.zip"

# NSE equity series we treat as "stocks/ETFs" for daily_prices.
EQUITY_SERIES = {"EQ", "BE", "BZ", "SM", "ST", "IV"}


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"user-agent": _UA, "accept": "*/*"})
    return s


def _fetch_zip_csv(url: str, timeout: int = 20) -> list[dict]:
    """Download a bhavcopy ZIP and return its single CSV as a list of dict rows."""
    r = _session().get(url, timeout=timeout)
    r.raise_for_status()
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    name = zf.namelist()[0]
    text = zf.read(name).decode("utf-8", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def fetch_cm_bhavcopy(dt: date) -> list[dict]:
    """Raw cash-market UDiFF rows for a given trading date. Raises on 404/holiday."""
    return _fetch_zip_csv(_CM_URL.format(ymd=dt.strftime("%Y%m%d")))


def fetch_fo_bhavcopy(dt: date) -> list[dict]:
    """Raw F&O UDiFF rows for a given trading date. Raises on 404/holiday."""
    return _fetch_zip_csv(_FO_URL.format(ymd=dt.strftime("%Y%m%d")))


def _walk_back(fetch, start: date, max_back: int = 7):
    """Try fetch(dt) walking back from `start` over trading days; return (dt, rows)."""
    dt = start
    last_err = None
    for _ in range(max_back + 1):
        if dt.weekday() < 5:  # skip Sat/Sun outright
            try:
                rows = fetch(dt)
                if rows:
                    return dt, rows
            except requests.HTTPError as e:
                last_err = e
        dt = dt - timedelta(days=1)
    raise RuntimeError(f"No bhavcopy found within {max_back} trading days of {start}: {last_err}")


def latest_cm_bhavcopy(on: date | None = None, max_back: int = 7) -> tuple[date, list[dict]]:
    """Most recent available CM bhavcopy on/before `on` (default today)."""
    return _walk_back(fetch_cm_bhavcopy, on or date.today(), max_back)


def latest_fo_bhavcopy(on: date | None = None, max_back: int = 7) -> tuple[date, list[dict]]:
    """Most recent available F&O bhavcopy on/before `on` (default today)."""
    return _walk_back(fetch_fo_bhavcopy, on or date.today(), max_back)


def cm_rows_by_symbol(rows: list[dict]) -> dict[str, dict]:
    """
    Map tradingsymbol -> row for equity/ETF series, preferring the 'EQ' series
    when a symbol appears in multiple series. Keyed on TckrSymb (== stocks.tradingsymbol).
    """
    out: dict[str, dict] = {}
    for row in rows:
        series = (row.get("SctySrs") or "").strip()
        if series not in EQUITY_SERIES:
            continue
        sym = (row.get("TckrSymb") or "").strip()
        if not sym:
            continue
        if sym not in out or series == "EQ":
            out[sym] = row
    return out


def parse_ohlcv(row: dict) -> dict:
    """Extract OHLCV from a UDiFF CM row into daily_prices-shaped floats/int."""
    def num(k):
        v = (row.get(k) or "").strip()
        return float(v) if v not in ("", "-") else None
    vol = (row.get("TtlTradgVol") or "").strip()
    return {
        "date": date.fromisoformat((row.get("TradDt") or "").strip()[:10]),
        "open": num("OpnPric"),
        "high": num("HghPric"),
        "low": num("LwPric"),
        "close": num("ClsPric"),
        "last": num("LastPric"),
        "volume": int(float(vol)) if vol not in ("", "-") else None,
    }
