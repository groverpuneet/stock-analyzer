"""
data_collectors/amfi_nav_collector.py

Free, non-brokerage mutual-fund NAV collector — the broker-free replacement for
MF NAV tracking.

Pulls AMFI India's public daily NAV dump (no auth, plain text):
    https://www.amfiindia.com/spages/NAVAll.txt

The file is semicolon-delimited and grouped by AMC. Actual NAV data lines have
six ';'-separated fields:

    Scheme Code;ISIN Div Payout/Growth;ISIN Div Reinvestment;Scheme Name;NAV;Date

AMC headers, section headers ("Open Ended Schemes(...)") and blank lines have
fewer than six fields and are skipped. The ISIN we want is matched against BOTH
ISIN columns (a scheme may key on either its growth/payout or reinvest ISIN).

Storage: an idempotent minimal `mf_nav(isin, nav, nav_date)` table with a
(isin, nav_date) unique constraint. MF watchlist ISINs come from
stocks.tradingsymbol WHERE instrument_type='MF'.

Table: mf_nav
Refresh log source: amfi_nav
"""
import os
import sys
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import requests

from utils.db import get_conn, refresh_log

log = logging.getLogger(__name__)

NAVALL_URL = "https://www.amfiindia.com/spages/NAVAll.txt"


def fetch_amfi_navs(wanted_isins: set) -> dict:
    """
    Download AMFI's NAVAll.txt and return {isin: (nav_float, 'DD-Mon-YYYY')} for
    every wanted ISIN found. Each wanted ISIN is matched against BOTH ISIN columns
    of every data line.
    """
    wanted = {i.strip() for i in wanted_isins if i and i.strip()}
    if not wanted:
        return {}

    r = requests.get(NAVALL_URL, timeout=30)
    r.raise_for_status()

    out: dict = {}
    for line in r.text.splitlines():
        parts = line.split(';')
        if len(parts) < 6:
            # AMC / section header / blank line
            continue
        isin1 = parts[1].strip()
        isin2 = parts[2].strip()
        nav_raw = parts[4].strip()
        date_raw = parts[5].strip()

        for isin in (isin1, isin2):
            if isin and isin != '-' and isin in wanted and isin not in out:
                try:
                    nav = float(nav_raw)
                except ValueError:
                    continue  # some schemes report 'N.A.' NAV
                out[isin] = (nav, date_raw)
    return out


def fetch_amfi_schemes() -> list:
    """
    Download AMFI's NAVAll.txt and return every scheme as a dict:
        {'amc', 'scheme_code', 'isin', 'isin2', 'name', 'nav', 'date'}
    'amc' is the AMC (fund house) header the scheme was listed under, tracked
    while parsing (AMC/section headers are the semicolon-less lines).
    """
    r = requests.get(NAVALL_URL, timeout=30)
    r.raise_for_status()

    schemes: list = []
    current_amc = ''
    for line in r.text.splitlines():
        if ';' not in line:
            stripped = line.strip()
            # Section headers describe scheme categories, not fund houses.
            if stripped and 'Scheme' not in stripped:
                current_amc = stripped
            continue
        parts = line.split(';')
        if len(parts) < 6:
            continue
        nav_raw = parts[4].strip()
        try:
            nav = float(nav_raw)
        except ValueError:
            nav = None
        schemes.append({
            'amc': current_amc,
            'scheme_code': parts[0].strip(),
            'isin': parts[1].strip(),
            'isin2': parts[2].strip(),
            'name': parts[3].strip(),
            'nav': nav,
            'date': parts[5].strip(),
        })
    return schemes


def _ensure_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS mf_nav (
            id        SERIAL PRIMARY KEY,
            isin      VARCHAR(20)   NOT NULL,
            nav       NUMERIC(14,4) NOT NULL,
            nav_date  DATE          NOT NULL,
            source    VARCHAR(20)   NOT NULL DEFAULT 'amfi',
            fetched_at TIMESTAMP     NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_mf_nav_isin_date UNIQUE (isin, nav_date)
        )
        """
    )


def collect_mf_navs() -> dict:
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        "SELECT tradingsymbol FROM stocks WHERE instrument_type = 'MF'"
    )
    wanted_isins = {row[0].strip() for row in cur.fetchall() if row[0]}
    log.info(f"Loaded {len(wanted_isins)} MF watchlist ISINs")

    navs = fetch_amfi_navs(wanted_isins)
    log.info(f"Resolved {len(navs)}/{len(wanted_isins)} ISINs from AMFI")

    upserted = 0
    with refresh_log('amfi_nav') as meta:
        _ensure_table(cur)
        conn.commit()
        for isin, (nav, date_str) in navs.items():
            nav_date = datetime.strptime(date_str, '%d-%b-%Y').date()
            cur.execute(
                """
                INSERT INTO mf_nav (isin, nav, nav_date, source, fetched_at)
                VALUES (%s, %s, %s, 'amfi', NOW())
                ON CONFLICT (isin, nav_date) DO UPDATE SET
                    nav        = EXCLUDED.nav,
                    fetched_at = EXCLUDED.fetched_at
                """,
                (isin, nav, nav_date),
            )
            upserted += 1
        conn.commit()
        meta['expected'] = len(wanted_isins)
        meta['rows'] = upserted

    cur.close()
    conn.close()

    missing = sorted(wanted_isins - set(navs))
    if missing:
        log.warning(f"{len(missing)} ISINs not found in AMFI feed: {missing}")

    log.info(f"mf_nav: {upserted} rows upserted for {len(navs)} ISINs")
    return {
        'wanted': len(wanted_isins),
        'resolved': len(navs),
        'rows_upserted': upserted,
        'missing': missing,
    }


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    result = collect_mf_navs()
    print(f"Done: {result}")
