"""
data_collectors/screener_pe_history_collector.py

Seeds historical P/E ratios (Screener.in chart API) into the fundamentals table,
so current P/E can be compared against the stock's own multi-year history.

Flow per watchlist stock:
  1. search API  -> Screener company_id (match exact /company/{SYMBOL}/ url)
  2. chart API   -> "Price to Earning" dataset (weekly, ~21yr available)
  3. downsample weekly -> monthly (last value per month), keep last ~10 years
  4. upsert into fundamentals (stock_id, date, pe_ratio) — one row per month

After seeding, compute_pe_percentiles() records, per stock, where the current
P/E sits within its own 5yr history (0 = cheapest, 100 = most expensive) into
stock_scores.pe_percentile.

Public Screener endpoints, no auth. Polite delay + 429 backoff.
"""
import os
import sys
import time
import logging
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import psycopg2

log = logging.getLogger(__name__)

DB_URL = os.environ.get("DATABASE_URL", "postgresql://puneetgrover@localhost/stock_analyzer")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "X-Requested-With": "XMLHttpRequest",
}
SEARCH_URL = "https://www.screener.in/api/company/search/"
CHART_URL = "https://www.screener.in/api/company/{cid}/chart/"
HISTORY_YEARS = 10
DELAY = 1.5


def _watchlist_nse(conn, watchlist="Default"):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT s.id, s.tradingsymbol FROM watchlist w JOIN stocks s ON w.stock_id = s.id
        WHERE w.name = %s AND s.exchange = 'NSE' ORDER BY s.tradingsymbol
        """,
        (watchlist,),
    )
    rows = cur.fetchall()
    cur.close()
    return rows


def _company_id(symbol: str) -> int | None:
    """Resolve a symbol to its Screener company_id by exact URL match."""
    r = requests.get(SEARCH_URL, headers=HEADERS, params={"q": symbol}, timeout=15)
    if r.status_code == 429:
        log.warning("  search 429 — sleeping 30s"); time.sleep(30)
        r = requests.get(SEARCH_URL, headers=HEADERS, params={"q": symbol}, timeout=15)
    r.raise_for_status()
    want = f"/company/{symbol}/".upper()
    for hit in r.json():
        if isinstance(hit, dict) and (hit.get("url") or "").upper().startswith(want):
            return hit.get("id")
    return None


def _pe_history(cid: int) -> list[tuple[date, float]]:
    """Fetch the 'Price to Earning' weekly series for a company_id."""
    r = requests.get(CHART_URL.format(cid=cid), headers=HEADERS,
                     params={"q": "Price to Earning-Median PE-EPS", "days": "10000"}, timeout=20)
    if r.status_code == 429:
        log.warning("  chart 429 — sleeping 30s"); time.sleep(30)
        r = requests.get(CHART_URL.format(cid=cid), headers=HEADERS,
                         params={"q": "Price to Earning-Median PE-EPS", "days": "10000"}, timeout=20)
    r.raise_for_status()
    series = []
    for ds in r.json().get("datasets", []):
        if ds.get("metric") == "Price to Earning":
            for pt in ds.get("values", []):
                d_str, val = pt[0], pt[1]
                if val is None:
                    continue
                try:
                    series.append((datetime.strptime(d_str, "%Y-%m-%d").date(), float(val)))
                except (ValueError, TypeError):
                    continue
    return series


def _monthly(series: list[tuple[date, float]], years: int) -> list[tuple[date, float]]:
    """Keep the last value per calendar month, within the last `years`."""
    cutoff = date.today().replace(year=date.today().year - years)
    by_month: dict[str, tuple[date, float]] = {}
    for d, v in sorted(series):
        if d < cutoff:
            continue
        by_month[f"{d.year}-{d.month:02d}"] = (d, v)  # last in month wins
    return sorted(by_month.values())


def seed_pe_history(watchlist="Default") -> dict:
    conn = psycopg2.connect(DB_URL)
    stocks = _watchlist_nse(conn, watchlist)
    log.info(f"Seeding PE history for {len(stocks)} NSE watchlist stocks ({HISTORY_YEARS}yr monthly)…")
    cur = conn.cursor()
    filled, total_rows, errors = 0, 0, []

    for stock_id, symbol in stocks:
        try:
            cid = _company_id(symbol)
            if not cid:
                errors.append({"symbol": symbol, "error": "no company_id"})
                log.warning(f"  {symbol}: no Screener company_id")
                time.sleep(DELAY); continue
            monthly = _monthly(_pe_history(cid), HISTORY_YEARS)
            n = 0
            for d, pe in monthly:
                cur.execute(
                    """
                    INSERT INTO fundamentals (stock_id, date, pe_ratio, source)
                    VALUES (%s, %s, %s, 'screener_pe_history')
                    ON CONFLICT (stock_id, date) DO UPDATE SET pe_ratio = EXCLUDED.pe_ratio
                    """,
                    (stock_id, d, round(pe, 2)),
                )
                n += 1
            conn.commit()
            total_rows += n
            if n:
                filled += 1
            log.info(f"  {symbol} (cid {cid}): {n} monthly PE points")
        except Exception as e:  # noqa: BLE001
            conn.rollback()
            errors.append({"symbol": symbol, "error": str(e)[:150]})
            log.warning(f"  {symbol}: FAILED — {str(e)[:120]}")
        time.sleep(DELAY)

    cur.close()
    conn.close()
    pctl = compute_pe_percentiles(watchlist)
    result = {"stocks": len(stocks), "stocks_filled": filled, "rows_upserted": total_rows,
              "pe_percentiles_set": pctl, "errors": errors}
    log.info(f"PE history seed done: {filled}/{len(stocks)} stocks, {total_rows} rows, "
             f"{pctl} percentiles, {len(errors)} errors")
    return result


def compute_pe_percentiles(watchlist="Default", years: int = 5) -> int:
    """For each watchlist stock: percentile of current P/E within its own `years`
    history (0=cheapest, 100=most expensive). Upsert into stock_scores.pe_percentile."""
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(
        "SELECT s.id FROM watchlist w JOIN stocks s ON w.stock_id = s.id WHERE w.name = %s",
        (watchlist,),
    )
    stock_ids = [r[0] for r in cur.fetchall()]
    today = date.today()
    cutoff = today.replace(year=today.year - years)
    set_count = 0

    for sid in stock_ids:
        # Use only the Screener chart series (one consistent earnings basis) — the
        # weekly `screener` top-ratio P/E can differ and would skew the percentile.
        cur.execute(
            "SELECT date, pe_ratio FROM fundamentals WHERE stock_id = %s "
            "AND source = 'screener_pe_history' AND pe_ratio IS NOT NULL AND pe_ratio > 0 "
            "ORDER BY date",
            (sid,),
        )
        rows = cur.fetchall()
        if len(rows) < 8:
            continue
        current_pe = float(rows[-1][1])
        hist = [float(pe) for d, pe in rows if d >= cutoff and pe is not None]
        if len(hist) < 8:
            hist = [float(pe) for _, pe in rows]
        below = sum(1 for v in hist if v <= current_pe)
        pct = round(100.0 * below / len(hist), 1)
        cur.execute(
            """
            INSERT INTO stock_scores (stock_id, date, pe_percentile)
            VALUES (%s, %s, %s)
            ON CONFLICT (stock_id, date) DO UPDATE SET pe_percentile = EXCLUDED.pe_percentile
            """,
            (sid, today, pct),
        )
        set_count += 1
    conn.commit()
    cur.close()
    conn.close()
    return set_count


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    res = seed_pe_history()
    print(f"\nDone: {res['stocks_filled']}/{res['stocks']} stocks, {res['rows_upserted']} PE rows, "
          f"{res['pe_percentiles_set']} percentiles, {len(res['errors'])} errors")
    for e in res["errors"][:10]:
        print(f"  ERR {e['symbol']}: {e['error']}")
