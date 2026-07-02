"""Add US stocks (Polygon.io) to the watchlist on demand.

The webapp watchlist search covers the local universe (NSE + already-seeded US) via
/api/stocks/search. This module adds *new* US tickers that aren't in the DB yet:
  - search_us_tickers(q): Polygon reference/tickers typeahead (NYSE/NASDAQ common stock)
  - add_us_stock(ticker): insert into stocks, fetch 2yr OHLCV, compute indicators,
    add to the watchlist. Ongoing daily updates are automatic — the us_raw_prices
    Dagster asset selects `market IN ('NYSE','NASDAQ')`.

Writes use the read-write DATABASE_URL (the collectors' connection), not the webapp's
read-only user, since this creates market data rows.
"""
import os
import sys
from datetime import date, timedelta

import psycopg2
import requests
from dotenv import dotenv_values

# Project root on sys.path so we can reuse the Polygon collector + indicator engine.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_ENV = dotenv_values(os.path.join(_ROOT, ".env"))
POLYGON_KEY = os.environ.get("POLYGON_API_KEY") or _ENV.get("POLYGON_API_KEY")
# Market-data writes need the read-write user (not the webapp read-only user).
_RW_DSN = os.environ.get("DATABASE_URL", "postgresql://puneetgrover@localhost/stock_analyzer")

TICKERS_URL = "https://api.polygon.io/v3/reference/tickers"

# Polygon primary_exchange MIC -> our exchange label
_MIC_TO_EXCHANGE = {
    "XNYS": "NYSE", "XNAS": "NASDAQ", "ARCX": "NYSE", "BATS": "NYSE",
    "XASE": "NYSE", "IEXG": "NYSE",
}


def _exchange(mic: str | None) -> str:
    return _MIC_TO_EXCHANGE.get(mic or "", "NYSE")


def search_us_tickers(q: str, limit: int = 10) -> list[dict]:
    """Polygon typeahead over active US common stocks. Returns market-badged rows."""
    if not q or not POLYGON_KEY:
        return []
    try:
        r = requests.get(
            TICKERS_URL,
            params={"search": q, "market": "stocks", "active": "true",
                    "type": "CS", "limit": limit, "apiKey": POLYGON_KEY},
            timeout=15,
        )
        r.raise_for_status()
    except Exception:
        return []
    out = []
    for t in r.json().get("results", []):
        exch = _exchange(t.get("primary_exchange"))
        out.append({
            "ticker": t["ticker"], "symbol": t["ticker"],
            "name": t.get("name"), "exchange": exch, "market": exch,
        })
    return out


def _ticker_details(ticker: str) -> dict:
    r = requests.get(f"{TICKERS_URL}/{ticker}", params={"apiKey": POLYGON_KEY}, timeout=15)
    r.raise_for_status()
    d = r.json().get("results", {})
    if not d:
        raise ValueError(f"Unknown ticker '{ticker}' on Polygon")
    return {"name": d.get("name") or ticker, "exchange": _exchange(d.get("primary_exchange"))}


def add_us_stock(ticker: str, watchlist: str = "Default") -> dict:
    """Insert a US stock (if new), fetch 2yr OHLCV, compute indicators, add to watchlist."""
    if not POLYGON_KEY:
        raise RuntimeError("POLYGON_API_KEY not configured")
    ticker = ticker.upper().strip()
    conn = psycopg2.connect(_RW_DSN)
    cur = conn.cursor()

    cur.execute(
        "SELECT id FROM stocks WHERE UPPER(tradingsymbol) = %s "
        "AND market IN ('NYSE','NASDAQ','US') LIMIT 1",
        (ticker,),
    )
    row = cur.fetchone()
    created = False
    if row:
        stock_id = row[0]
    else:
        meta = _ticker_details(ticker)
        # Synthetic instrument_token in the reserved US band [9.0e9, 9.1e9).
        cur.execute(
            "SELECT COALESCE(MAX(instrument_token), 9000000029) + 1 FROM stocks "
            "WHERE instrument_token >= 9000000000 AND instrument_token < 9100000000"
        )
        synthetic_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO stocks (instrument_token, tradingsymbol, name, exchange,
                                segment, market, instrument_type)
            VALUES (%s, %s, %s, %s, %s, %s, 'EQ') RETURNING id
            """,
            (synthetic_id, ticker, meta["name"], meta["exchange"], meta["exchange"], meta["exchange"]),
        )
        stock_id = cur.fetchone()[0]
        conn.commit()
        created = True

    # Fetch ~2yr of daily bars (single Polygon call) and store.
    from data_collectors.polygon_prices_collector import _fetch_bars, _store
    to = date.today()
    frm = to - timedelta(days=730)
    session = requests.Session()
    bars = _fetch_bars(session, ticker, frm.isoformat(), to.isoformat(), POLYGON_KEY)
    stored = _store(stock_id, bars)

    # Compute technical + volume indicators over the fetched history.
    from analysis.calculate_indicators import calculate_all_indicators
    try:
        calculate_all_indicators(stock_id, ticker, limit=600)
    except Exception:
        pass  # indicators need ~50 bars; a brand-new listing may have fewer

    # Add to the named watchlist (idempotent).
    cur.execute("SELECT id FROM watchlist WHERE stock_id = %s AND name = %s", (stock_id, watchlist))
    if not cur.fetchone():
        cur.execute("INSERT INTO watchlist (stock_id, name) VALUES (%s, %s)", (stock_id, watchlist))
        conn.commit()
    cur.close()
    conn.close()
    return {"stock_id": stock_id, "ticker": ticker, "created": created, "bars": stored}
