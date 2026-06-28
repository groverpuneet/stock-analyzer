"""
data_collectors/sec_form4_collector.py

Collects US insider transactions (SEC Form 4) for the seeded US stock universe
and stores them in insider_trades with source='sec_form4'.

Source: SEC EDGAR (free, no key). Requires a descriptive User-Agent with a contact
email per SEC fair-access policy; SEC accepts Python's requests TLS (unlike FRED).

Pipeline per US stock:
  1. Resolve ticker -> CIK via www.sec.gov/files/company_tickers.json (fetched once).
  2. data.sec.gov/submissions/CIK<cik>.json -> recent filings; keep form == '4'
     filed within the lookback window.
  3. Fetch each Form 4 ownership XML and parse the non-derivative transaction table
     (actual share acquisitions/disposals — the highest-signal insider activity).

Mapping into insider_trades:
  date            = transactionDate
  person_name     = reporting owner name
  person_category = relationship (Director / Officer:<title> / 10% Owner)
  transaction     = 'BUY' (code P) / 'SELL' (code S) / raw code (M,F,A,G,X,C,...)
  quantity        = transactionShares
  price           = transactionPricePerShare (NULL for grants/exercises with no price)
  source          = 'sec_form4'
Upsert on the existing unique key (stock_id, date, person_name, transaction, quantity).

Schedule: daily via the us_insider_trades Dagster asset.
"""
import os
import sys
import time
import logging
import xml.etree.ElementTree as ET
from datetime import date, timedelta

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import get_conn, refresh_log

log = logging.getLogger(__name__)

# SEC requires a real contact in the UA. Reuse the project owner's email.
_UA = {"User-Agent": "stock-analyzer research manya.s.187@gmail.com"}
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVE_DOC = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"

_THROTTLE_S = 0.15  # stay well under SEC's 10 req/s guidance
_LOOKBACK_DAYS = 30
# Open-market transaction codes worth a clean BUY/SELL label; others kept as raw code.
_CODE_LABEL = {"P": "BUY", "S": "SELL"}


def _val(parent, path):
    """Form 4 leaf values are sometimes wrapped in a <value> child, sometimes not."""
    el = parent.find(path)
    if el is None:
        return None
    v = el.find("value")
    text = v.text if v is not None else el.text
    return text.strip() if text else None


def _ticker_cik_map(session) -> dict:
    data = session.get(TICKERS_URL, timeout=30).json()
    return {row["ticker"].upper(): str(row["cik_str"]).zfill(10) for row in data.values()}


def _us_stocks() -> list[tuple]:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT id, tradingsymbol FROM stocks WHERE market IN ('NYSE','NASDAQ') ORDER BY tradingsymbol")
    rows = cur.fetchall(); cur.close(); conn.close()
    return rows


def _recent_form4_accessions(session, cik: str, since: date) -> list[tuple]:
    """Return [(accession_no_dashes, primary_document), ...] for Form 4s filed since `since`."""
    resp = session.get(SUBMISSIONS_URL.format(cik=cik), timeout=30)
    resp.raise_for_status()
    recent = resp.json().get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accs = recent.get("accessionNumber", [])
    docs = recent.get("primaryDocument", [])
    dates = recent.get("filingDate", [])
    out = []
    for i, form in enumerate(forms):
        if form != "4":
            continue
        if dates[i] < since.isoformat():
            continue
        out.append((accs[i].replace("-", ""), docs[i]))
    return out


def _category(rel) -> str:
    if rel is None:
        return ""
    parts = []
    if _val(rel, "isDirector") in ("1", "true"):
        parts.append("Director")
    if _val(rel, "isOfficer") in ("1", "true"):
        title = _val(rel, "officerTitle")
        parts.append(f"Officer:{title}" if title else "Officer")
    if _val(rel, "isTenPercentOwner") in ("1", "true"):
        parts.append("10% Owner")
    if _val(rel, "isOther") in ("1", "true"):
        parts.append("Other")
    return ", ".join(parts)[:60]


def _parse_form4(xml_bytes: bytes) -> list[dict]:
    """Parse non-derivative transactions out of a Form 4 ownership document."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    owner = root.find("reportingOwner")
    name = (_val(owner, "reportingOwnerId/rptOwnerName") or "")[:200] if owner is not None else ""
    category = _category(owner.find("reportingOwnerRelationship") if owner is not None else None)

    rows = []
    for t in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        tdate = _val(t, "transactionDate")
        shares = _val(t, "transactionAmounts/transactionShares")
        if not tdate or not shares:
            continue
        code = _val(t, "transactionCoding/transactionCode") or ""
        price = _val(t, "transactionAmounts/transactionPricePerShare")
        transaction = _CODE_LABEL.get(code, code)[:10]
        try:
            qty = int(round(float(shares)))
        except ValueError:
            continue
        try:
            price_v = float(price) if price else None
        except ValueError:
            price_v = None
        rows.append({
            "date": tdate, "person_name": name, "person_category": category,
            "transaction": transaction, "quantity": qty, "price": price_v,
        })
    return rows


def _store(stock_id: int, txns: list[dict]) -> int:
    if not txns:
        return 0
    conn = get_conn(); cur = conn.cursor()
    n = 0
    for tx in txns:
        cur.execute(
            """
            INSERT INTO insider_trades
                (stock_id, date, person_name, person_category, transaction, quantity, price, source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'sec_form4')
            ON CONFLICT (stock_id, date, person_name, transaction, quantity) DO NOTHING
            """,
            (stock_id, tx["date"], tx["person_name"], tx["person_category"],
             tx["transaction"], tx["quantity"], tx["price"]),
        )
        n += cur.rowcount
    conn.commit(); cur.close(); conn.close()
    return n


def collect_sec_form4(lookback_days: int = _LOOKBACK_DAYS) -> dict:
    """Fetch Form 4 insider transactions for the US universe into insider_trades."""
    log.info(f"=== SEC Form 4 collection starting (lookback {lookback_days}d) ===")
    since = date.today() - timedelta(days=lookback_days)
    session = requests.Session()
    session.headers.update(_UA)

    with refresh_log("sec_form4") as meta:
        cik_map = _ticker_cik_map(session)
        total = 0
        stocks_with_data = 0
        for stock_id, symbol in _us_stocks():
            cik = cik_map.get(symbol.upper())
            if not cik:
                log.warning(f"  {symbol}: no CIK match — skipping")
                continue
            try:
                filings = _recent_form4_accessions(session, cik, since)
            except Exception as e:
                log.warning(f"  {symbol}: submissions fetch failed: {e}")
                continue
            time.sleep(_THROTTLE_S)
            sym_rows = []
            for acc, doc in filings:
                raw_doc = doc.rsplit("/", 1)[-1]  # strip xslF345X##/ render prefix
                url = ARCHIVE_DOC.format(cik=int(cik), acc=acc, doc=raw_doc)
                try:
                    r = session.get(url, timeout=30)
                    if r.status_code == 200:
                        sym_rows.extend(_parse_form4(r.content))
                except Exception as e:
                    log.debug(f"  {symbol} {acc}: doc fetch failed: {e}")
                time.sleep(_THROTTLE_S)
            stored = _store(stock_id, sym_rows)
            total += stored
            if stored:
                stocks_with_data += 1
            log.info(f"  {symbol}: {len(filings)} Form 4 filings, {len(sym_rows)} txns, {stored} new")
        meta["rows"] = total

    log.info(f"sec_form4: {total} new insider transactions across {stocks_with_data} stocks")
    return {"rows_upserted": total, "stocks_with_data": stocks_with_data}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = collect_sec_form4()
    print(f"Done: {result}")
