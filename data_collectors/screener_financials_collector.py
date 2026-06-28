"""
data_collectors/screener_financials_collector.py

One Screener page fetch per watchlist stock, extracting (Parts 6/7/8/10):
  - Quarterly results (last ~12 q): Sales->revenue, Operating Profit->ebitda,
    Net Profit->pat, EPS  -> earnings_calendar + quarterly_financials
  - Latest annual debt (Borrowings) + OCF (Cash from Operating Activity) attached
    to the most recent quarter row (Screener has no quarterly BS/CF)
  - Concall transcript links -> concall_transcripts (URLs only; text/summary on demand)
  - Sector / industry -> stocks (best-effort from the peers fragment)

Public Screener pages, polite delay. ON CONFLICT upserts everywhere.
"""
import os
import sys
import time
import logging
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from bs4 import BeautifulSoup
import psycopg2

log = logging.getLogger(__name__)
DB_URL = os.environ.get("DATABASE_URL", "postgresql://puneetgrover@localhost/stock_analyzer")
H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
DELAY = 1.2

_MONTH_END = {"Mar": (3, 31), "Jun": (6, 30), "Sep": (9, 30), "Dec": (12, 31),
              "Jan": (1, 31), "Feb": (2, 28), "Apr": (4, 30), "May": (5, 31),
              "Jul": (7, 31), "Aug": (8, 31), "Oct": (10, 31), "Nov": (11, 30)}


def _num(t):
    if not t:
        return None
    t = t.replace(",", "").replace("%", "").replace("₹", "").strip()
    try:
        return float(t)
    except ValueError:
        return None


def _period_end(label: str):
    """'Jun 2025' -> date(2025, 6, 30)."""
    try:
        mon, yr = label.split()
        m, d = _MONTH_END[mon[:3]]
        return date(int(yr), m, d)
    except Exception:  # noqa: BLE001
        return None


def _section_table(soup, sel):
    """Return (header labels, {row_label: [cell values...]}) for a Screener section table."""
    s = soup.select_one(sel)
    if not s:
        return [], {}
    heads = [th.get_text(strip=True) for th in s.select("thead th")]
    rows = {}
    for tr in s.select("tbody tr"):
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue
        label = cells[0].get_text(strip=True).rstrip("+").strip()
        rows[label] = [c.get_text(strip=True) for c in cells[1:]]
    return heads, rows


def _fetch(symbol: str):
    url = f"https://www.screener.in/company/{symbol}/consolidated/"
    r = requests.get(url, headers=H, timeout=20)
    if r.status_code == 404:
        r = requests.get(f"https://www.screener.in/company/{symbol}/", headers=H, timeout=20)
    r.raise_for_status()
    return BeautifulSoup(r.text, "lxml"), r.text


def collect_financials(watchlist="Default") -> dict:
    from utils.db import refresh_log
    with refresh_log("quarterly_financials") as meta:
        result = _collect_financials(watchlist)
        meta["rows"] = result["quarterly_rows"]
        meta["expected"] = result["stocks"]
        meta["gaps"] = [e["symbol"] for e in result["errors"]]
    return result


def _collect_financials(watchlist="Default") -> dict:
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT s.id, s.tradingsymbol FROM watchlist w JOIN stocks s ON w.stock_id=s.id "
                "WHERE w.name=%s AND s.exchange='NSE' ORDER BY s.tradingsymbol", (watchlist,))
    stocks = cur.fetchall()
    log.info(f"Financials: {len(stocks)} NSE watchlist stocks…")

    q_rows, ec_rows, concalls, sectors, errors = 0, 0, 0, 0, []
    for sid, sym in stocks:
        try:
            soup, html = _fetch(sym)
            heads, q = _section_table(soup, "#quarters table")
            bs_heads, bs = _section_table(soup, "#balance-sheet table")
            cf_heads, cf = _section_table(soup, "#cash-flow table")

            sales = q.get("Sales") or q.get("Revenue") or q.get("Total Revenue") or []
            opro = q.get("Operating Profit") or []
            npro = q.get("Net Profit") or []
            eps = q.get("EPS in Rs") or q.get("EPS") or []

            # latest annual debt + OCF (no quarterly BS/CF on Screener)
            borrow = _num((bs.get("Borrowings") or [None])[-1]) if bs.get("Borrowings") else None
            ocf = _num((cf.get("Cash from Operating Activity") or [None])[-1]) if cf.get("Cash from Operating Activity") else None

            for i, qlabel in enumerate(heads):
                pe = _period_end(qlabel)
                if not pe:
                    continue
                rev = _num(sales[i]) if i < len(sales) else None
                ebitda = _num(opro[i]) if i < len(opro) else None
                pat = _num(npro[i]) if i < len(npro) else None
                e = _num(eps[i]) if i < len(eps) else None
                if rev is None and pat is None and e is None:
                    continue
                is_latest = (i == len(heads) - 1)
                cur.execute("""
                    INSERT INTO quarterly_financials (stock_id, quarter, period_end, revenue, ebitda, pat, eps, debt, ocf)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (stock_id, period_end) DO UPDATE SET
                      revenue=EXCLUDED.revenue, ebitda=EXCLUDED.ebitda, pat=EXCLUDED.pat, eps=EXCLUDED.eps,
                      debt=COALESCE(EXCLUDED.debt, quarterly_financials.debt),
                      ocf=COALESCE(EXCLUDED.ocf, quarterly_financials.ocf), updated_at=now()
                """, (sid, qlabel, pe, rev, ebitda, pat, e, borrow if is_latest else None, ocf if is_latest else None))
                q_rows += 1
                # results_date estimated (Indian co's announce ~45d after quarter end)
                cur.execute("""
                    INSERT INTO earnings_calendar (stock_id, quarter, period_end, results_date, revenue_actual, pat_actual, eps_actual, source)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,'screener')
                    ON CONFLICT (stock_id, period_end) DO UPDATE SET
                      revenue_actual=EXCLUDED.revenue_actual, pat_actual=EXCLUDED.pat_actual,
                      eps_actual=EXCLUDED.eps_actual, quarter=EXCLUDED.quarter
                """, (sid, qlabel, pe, pe + timedelta(days=45), rev, pat, e))
                ec_rows += 1

            # concall transcript links
            for a in soup.select("a"):
                if a.get_text(strip=True) == "Transcript" and a.get("href"):
                    cur.execute("""
                        INSERT INTO concall_transcripts (stock_id, quarter, transcript_url, source)
                        VALUES (%s,%s,%s,'screener')
                        ON CONFLICT (stock_id, quarter) DO UPDATE SET transcript_url=EXCLUDED.transcript_url
                    """, (sid, heads[-1] if heads else None, a.get("href")))
                    concalls += 1
                    break  # latest transcript only

            # sector/industry — best effort from the company "About"/peers classification
            sector, industry = _sector_industry(soup, html)
            if sector or industry:
                cur.execute("UPDATE stocks SET sector=COALESCE(%s, sector), industry=COALESCE(%s, industry) WHERE id=%s",
                            (sector, industry, sid))
                sectors += 1

            conn.commit()
            log.info(f"  {sym}: {len([h for h in heads if _period_end(h)])} quarters, sector={industry or sector}")
        except Exception as e:  # noqa: BLE001
            conn.rollback()
            errors.append({"symbol": sym, "error": str(e)[:150]})
            log.warning(f"  {sym}: FAILED — {str(e)[:120]}")
        time.sleep(DELAY)

    cur.close()
    conn.close()
    result = {"stocks": len(stocks), "quarterly_rows": q_rows, "earnings_rows": ec_rows,
              "concalls": concalls, "sectors": sectors, "errors": errors}
    log.info(f"Financials done: {result}")
    return result


def _sector_industry(soup, html):
    """Screener classifies each company via a /market/ hierarchy in the #peers block:
    macro-sector > sector > industry > sub-industry (e.g. Energy > Oil, Gas... >
    Petroleum Products > Refineries & Marketing). Take the top level as `sector`
    and the most granular as `industry`."""
    peers = soup.select_one("#peers") or soup
    crumbs = [a.get_text(strip=True) for a in peers.select('a[href*="/market/"]')
              if a.get_text(strip=True)]
    if not crumbs:
        return None, None
    sector = crumbs[0]
    industry = crumbs[-1] if len(crumbs) > 1 else None
    return sector, industry


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    r = collect_financials()
    print(f"\nDone: {r['quarterly_rows']} quarterly rows, {r['earnings_rows']} earnings, "
          f"{r['concalls']} concalls, {r['sectors']} sectors, {len(r['errors'])} errors")
