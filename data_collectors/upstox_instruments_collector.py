"""
data_collectors/upstox_instruments_collector.py

Syncs the Upstox instrument master into the DB:
  - F&O contracts (FUT/CE/PE)  -> fno_instruments  (full upsert)
  - Equity instrument_key/isin -> stocks           (UPDATE existing rows only, so
                                                     Upstox candle calls can resolve)

Source: public Upstox instrument dump — NO auth, no account required:
  https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz
Format: gzip-compressed JSON array. Refreshed daily ~6 AM IST.

This is the foundation every other Upstox collector keys off (historical candles,
quotes, option chain all reference instrument_key). Because it needs no token, it
is fully testable before the Upstox account/Analytics token exists.

Refresh tag: upstox_instruments. Schedule: daily via the nse_upstox_instruments asset.
"""
import os
import sys
import gzip
import json
import logging
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import get_conn, refresh_log

load_dotenv()
log = logging.getLogger(__name__)

# Public static dumps — no auth. Add "BSE" to also pull BSE equities/derivatives.
_INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/{exchange}.json.gz"
_EXCHANGES = ["NSE"]
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36")
_HTTP_TIMEOUT = 60


def _fetch_instruments(exchange: str) -> list[dict]:
    """Download + gunzip + parse one exchange's instrument dump (public, no auth)."""
    url = _INSTRUMENTS_URL.format(exchange=exchange)
    resp = requests.get(url, headers={"user-agent": _UA, "accept": "*/*"}, timeout=_HTTP_TIMEOUT)
    resp.raise_for_status()
    return json.loads(gzip.decompress(resp.content))


def _epoch_ms_to_date(v):
    """Upstox encodes expiry as epoch-ms; return a date or None."""
    if v in (None, 0, ""):
        return None
    try:
        return datetime.fromtimestamp(int(v) / 1000, tz=timezone.utc).date()
    except (ValueError, TypeError, OSError):
        return None


def _upsert_fno(rows: list[dict]) -> int:
    """Full upsert of F&O contracts into fno_instruments (keyed on instrument_key)."""
    conn = get_conn(); cur = conn.cursor()
    n = 0
    for r in rows:
        expiry = _epoch_ms_to_date(r.get("expiry"))
        if expiry is None:
            continue  # a derivatives row without a resolvable expiry — skip
        underlying_key = r.get("underlying_key") or ""
        underlying_type = "INDEX" if "_INDEX" in underlying_key else "EQUITY"
        cur.execute(
            """
            INSERT INTO fno_instruments (
                instrument_key, exchange_token, tradingsymbol, name,
                underlying_symbol, underlying_key, underlying_type,
                exchange, segment, instrument_type, expiry, strike,
                lot_size, tick_size, freeze_quantity, isin)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (instrument_key) DO UPDATE SET
                tradingsymbol=EXCLUDED.tradingsymbol, name=EXCLUDED.name,
                underlying_symbol=EXCLUDED.underlying_symbol,
                underlying_key=EXCLUDED.underlying_key,
                underlying_type=EXCLUDED.underlying_type,
                exchange=EXCLUDED.exchange, segment=EXCLUDED.segment,
                instrument_type=EXCLUDED.instrument_type, expiry=EXCLUDED.expiry,
                strike=EXCLUDED.strike, lot_size=EXCLUDED.lot_size,
                tick_size=EXCLUDED.tick_size, freeze_quantity=EXCLUDED.freeze_quantity,
                isin=EXCLUDED.isin, updated_at=NOW()
            """,
            (r.get("instrument_key"), r.get("exchange_token"),
             r.get("trading_symbol"), r.get("name"),
             r.get("underlying_symbol"), underlying_key, underlying_type,
             r.get("exchange"), r.get("segment"), r.get("instrument_type"),
             expiry, r.get("strike_price") or None,
             r.get("lot_size"), r.get("tick_size"), r.get("freeze_quantity"),
             r.get("isin")),
        )
        n += 1
    conn.commit(); cur.close(); conn.close()
    return n


def _update_equity_keys(rows: list[dict]) -> int:
    """Stamp instrument_key + isin onto EXISTING stocks rows (match tradingsymbol+exchange).

    Deliberately does NOT insert new stocks — flooding `stocks` with the full NSE
    universe would change every watchlist-scoped pipeline. Universe expansion stays
    a separate, explicit action (data_collectors/expand_stock_universe.py).
    """
    conn = get_conn(); cur = conn.cursor()
    n = 0
    for r in rows:
        cur.execute(
            "UPDATE stocks SET instrument_key=%s, isin=COALESCE(%s, isin) "
            "WHERE tradingsymbol=%s AND exchange=%s",
            (r.get("instrument_key"), r.get("isin"),
             r.get("trading_symbol"), r.get("exchange")),
        )
        n += cur.rowcount
    conn.commit(); cur.close(); conn.close()
    return n


def collect_upstox_instruments() -> dict:
    """Sync the Upstox instrument master: F&O -> fno_instruments, equity keys -> stocks."""
    with refresh_log("upstox_instruments") as meta:
        all_rows: list[dict] = []
        for ex in _EXCHANGES:
            rows = _fetch_instruments(ex)
            log.info(f"  {ex}: {len(rows)} instruments downloaded")
            all_rows.extend(rows)

        fno = [r for r in all_rows
               if r.get("instrument_type") in ("FUT", "CE", "PE")
               and str(r.get("segment", "")).endswith("_FO")]
        eq = [r for r in all_rows
              if r.get("instrument_type") == "EQ"
              and str(r.get("segment", "")).endswith("_EQ")]

        n_fno = _upsert_fno(fno)
        n_eq = _update_equity_keys(eq)
        meta["rows"] = n_fno + n_eq
        log.info(f"upstox_instruments: {n_fno} F&O contracts upserted, {n_eq} equities keyed")

    return {"fno_upserted": n_fno, "equities_keyed": n_eq}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = collect_upstox_instruments()
    print(f"Done: {result}")
