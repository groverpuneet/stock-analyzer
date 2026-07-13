"""
data_collectors/sec_13f_collector.py
Quarterly refresh — US weekly group

Fetches SEC 13F-HR institutional holdings filings for tracked filers.
Source: SEC EDGAR (free, requires User-Agent with contact email).

Usage:
    python data_collectors/sec_13f_collector.py
    python data_collectors/sec_13f_collector.py --filer "Berkshire Hathaway"
    python data_collectors/sec_13f_collector.py --backfill 2
"""
import os
import sys
import time
import re
import xml.etree.ElementTree as ET
from datetime import datetime, date
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import get_conn, refresh_log
from utils.logger import get_logger

log = get_logger(__name__)

SEC_HEADERS = {
    'User-Agent': 'stock-analyzer (manya.s.187@gmail.com)',
    'Accept': 'application/json, application/xml, */*',
}

# CUSIP to ticker mapping (partial - will be extended)
CUSIP_TO_TICKER = {
    '594918104': 'MSFT',
    '037833100': 'AAPL',
    '02079K107': 'GOOG',
    '02079K305': 'GOOGL',
    '023135106': 'AMZN',
    '30303M102': 'META',
    '67066G104': 'NVDA',
    '88160R101': 'TSLA',
    '11135F101': 'AVGO',
}


def get_tracked_filers() -> list:
    """Get list of tracked filers from DB."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, filer_name, filer_cik, category
        FROM tracked_filers
        WHERE active = true
        ORDER BY filer_name
    """)
    filers = cursor.fetchall()
    cursor.close()
    conn.close()
    return filers


def get_filer_13f_filings(cik: str, count: int = 4) -> list:
    """
    Get recent 13F-HR filings for a filer.
    Returns list of (accession_number, filing_date, quarter).
    """
    import requests

    # Pad CIK to 10 digits
    cik_padded = cik.zfill(10)
    url = f'https://data.sec.gov/submissions/CIK{cik_padded}.json'

    resp = requests.get(url, headers=SEC_HEADERS, timeout=15)
    if resp.status_code != 200:
        log.warning(f"Failed to get submissions for CIK {cik}: {resp.status_code}")
        return []

    data = resp.json()
    filings = data.get('filings', {}).get('recent', {})
    forms = filings.get('form', [])
    accessions = filings.get('accessionNumber', [])
    dates = filings.get('filingDate', [])

    results = []
    for i, form in enumerate(forms):
        if '13F-HR' in form and len(results) < count:
            filing_date = dates[i]
            # Determine quarter from filing date
            # 13F filed within 45 days of quarter end
            fd = datetime.strptime(filing_date, '%Y-%m-%d').date()
            # Q1 (Jan-Mar) -> filed by May 15
            # Q2 (Apr-Jun) -> filed by Aug 14
            # Q3 (Jul-Sep) -> filed by Nov 14
            # Q4 (Oct-Dec) -> filed by Feb 14
            if fd.month <= 2:
                quarter = f"{fd.year - 1}Q4"
            elif fd.month <= 5:
                quarter = f"{fd.year}Q1"
            elif fd.month <= 8:
                quarter = f"{fd.year}Q2"
            elif fd.month <= 11:
                quarter = f"{fd.year}Q3"
            else:
                quarter = f"{fd.year}Q4"

            results.append((accessions[i], filing_date, quarter))

    return results


def fetch_13f_holdings(cik: str, accession: str) -> list:
    """
    Fetch holdings from a 13F-HR filing.
    Returns list of holding dicts.
    """
    import requests

    cik_clean = str(int(cik))  # Remove leading zeros
    accession_clean = accession.replace('-', '')

    # Get filing index to find info table file
    index_url = f'https://www.sec.gov/Archives/edgar/data/{cik_clean}/{accession_clean}/index.json'
    resp = requests.get(index_url, headers=SEC_HEADERS, timeout=15)

    if resp.status_code != 200:
        log.warning(f"Failed to get filing index: {resp.status_code}")
        return []

    # Find the XML info table file (largest XML file)
    items = resp.json().get('directory', {}).get('item', [])
    xml_files = [(i.get('name'), int(i.get('size') or 0)) for i in items if i.get('name', '').endswith('.xml')]
    xml_files.sort(key=lambda x: x[1], reverse=True)

    if not xml_files:
        log.warning(f"No XML files found in filing {accession}")
        return []

    # Get the largest XML (info table)
    xml_name = xml_files[0][0]
    xml_url = f'https://www.sec.gov/Archives/edgar/data/{cik_clean}/{accession_clean}/{xml_name}'

    time.sleep(0.15)  # SEC rate limit
    resp = requests.get(xml_url, headers=SEC_HEADERS, timeout=30)

    if resp.status_code != 200:
        log.warning(f"Failed to fetch XML: {resp.status_code}")
        return []

    # Parse XML
    holdings = []
    try:
        root = ET.fromstring(resp.text)

        # Remove namespace for easier parsing
        for elem in root.iter():
            if '}' in elem.tag:
                elem.tag = elem.tag.split('}')[1]

        # Find info table entries
        for entry in root.findall('.//infoTable'):
            holding = {}
            for child in entry:
                tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                holding[tag] = child.text.strip() if child.text else None

                # Handle nested elements (shrsOrPrnAmt, votingAuthority)
                if list(child):
                    for subchild in child:
                        subtag = subchild.tag.split('}')[-1] if '}' in subchild.tag else subchild.tag
                        holding[subtag] = subchild.text.strip() if subchild.text else None

            if holding.get('cusip'):
                holdings.append({
                    'cusip': holding.get('cusip'),
                    'issuer_name': holding.get('nameOfIssuer'),
                    'title_of_class': holding.get('titleOfClass'),
                    'shares_held': int(holding.get('sshPrnamt') or 0),
                    'market_value_usd': int(holding.get('value') or 0),
                    'symbol': CUSIP_TO_TICKER.get(holding.get('cusip')),
                })

    except ET.ParseError as e:
        log.error(f"XML parse error: {e}")

    return holdings


def calculate_portfolio_weights(holdings: list) -> list:
    """Calculate percentage of portfolio for each holding."""
    total_value = sum(h.get('market_value_usd', 0) for h in holdings)
    if total_value == 0:
        return holdings

    for h in holdings:
        h['pct_of_portfolio'] = round(h.get('market_value_usd', 0) / total_value * 100, 4)

    return holdings


def get_previous_quarter_holdings(filer_cik: str, quarter: str) -> dict:
    """Get previous quarter holdings for QoQ comparison."""
    conn = get_conn()
    cursor = conn.cursor()

    # Calculate previous quarter
    year, q = int(quarter[:4]), int(quarter[5])
    if q == 1:
        prev_quarter = f"{year - 1}Q4"
    else:
        prev_quarter = f"{year}Q{q - 1}"

    cursor.execute("""
        SELECT cusip, shares_held
        FROM institutional_holdings_13f
        WHERE filer_cik = %s AND quarter = %s
    """, (filer_cik, prev_quarter))

    prev_holdings = {row[0]: row[1] for row in cursor.fetchall()}
    cursor.close()
    conn.close()
    return prev_holdings


def store_holdings(filer_id: int, filer_cik: str, quarter: str, filing_date: str, holdings: list) -> int:
    """Store 13F holdings in database."""
    conn = get_conn()
    cursor = conn.cursor()
    count = 0

    # Get previous quarter for QoQ comparison
    prev_holdings = get_previous_quarter_holdings(filer_cik, quarter)

    for h in holdings:
        prev_shares = prev_holdings.get(h['cusip'])
        qoq_change_shares = None
        qoq_change_pct = None

        if prev_shares is not None and prev_shares > 0:
            qoq_change_shares = h['shares_held'] - prev_shares
            qoq_change_pct = round((h['shares_held'] - prev_shares) / prev_shares * 100, 2)

        try:
            cursor.execute("""
                INSERT INTO institutional_holdings_13f
                    (filer_id, filer_cik, quarter, symbol, cusip, issuer_name,
                     title_of_class, shares_held, market_value_usd, pct_of_portfolio,
                     qoq_change_shares, qoq_change_pct, filing_date, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'sec_13f')
                ON CONFLICT (filer_cik, quarter, cusip) DO UPDATE SET
                    shares_held = EXCLUDED.shares_held,
                    market_value_usd = EXCLUDED.market_value_usd,
                    pct_of_portfolio = EXCLUDED.pct_of_portfolio,
                    qoq_change_shares = EXCLUDED.qoq_change_shares,
                    qoq_change_pct = EXCLUDED.qoq_change_pct
            """, (
                filer_id, filer_cik, quarter, h.get('symbol'), h['cusip'], h['issuer_name'],
                h['title_of_class'], h['shares_held'], h['market_value_usd'], h.get('pct_of_portfolio'),
                qoq_change_shares, qoq_change_pct, filing_date
            ))
            count += 1
        except Exception as e:
            log.error(f"Store holding failed: {e}")
            conn.rollback()

    conn.commit()
    cursor.close()
    conn.close()
    return count


def collect_13f_holdings(filer_name: str = None, quarters: int = 2):
    """
    Collect 13F holdings for tracked filers.
    """
    print(f"\n{'='*60}")
    print("SEC 13F INSTITUTIONAL HOLDINGS COLLECTOR")
    print(f"{'='*60}")

    filers = get_tracked_filers()

    if filer_name:
        filers = [(fid, fn, cik, cat) for fid, fn, cik, cat in filers if filer_name.lower() in fn.lower()]

    print(f"Filers: {len(filers)}  |  Quarters to fetch: {quarters}\n")

    with refresh_log('sec_13f') as rlog:
        rlog['expected'] = len(filers) * quarters
        total_holdings = 0

        for filer_id, fname, cik, category in filers:
            print(f"\n{fname} (CIK: {cik}):")

            filings = get_filer_13f_filings(cik, count=quarters)
            if not filings:
                print(f"  ⚠ No 13F filings found")
                continue

            for accession, filing_date, quarter in filings:
                print(f"  {quarter} (filed {filing_date}):")

                holdings = fetch_13f_holdings(cik, accession)
                if not holdings:
                    print(f"    ⚠ No holdings parsed")
                    continue

                holdings = calculate_portfolio_weights(holdings)
                count = store_holdings(filer_id, cik, quarter, filing_date, holdings)
                total_holdings += count

                # Show top 5 holdings
                top5 = sorted(holdings, key=lambda x: x.get('market_value_usd', 0), reverse=True)[:5]
                for h in top5:
                    sym = h.get('symbol') or h['cusip'][:6]
                    val = h['market_value_usd'] / 1e6
                    pct = h.get('pct_of_portfolio', 0)
                    print(f"    {sym:<8} ${val:>10,.0f}M  ({pct:.1f}%)")

                time.sleep(0.5)  # Rate limit

        rlog['rows'] = total_holdings

    # Print summary
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT tf.filer_name, h.quarter, COUNT(*) as holdings, SUM(h.market_value_usd)/1e9 as aum_b
        FROM institutional_holdings_13f h
        JOIN tracked_filers tf ON tf.id = h.filer_id
        GROUP BY tf.filer_name, h.quarter
        ORDER BY tf.filer_name, h.quarter DESC
    """)
    summary = cursor.fetchall()
    cursor.close()
    conn.close()

    if summary:
        print(f"\n{'='*60}")
        print(f"HOLDINGS SUMMARY")
        print(f"{'='*60}")
        for fname, quarter, count, aum in summary:
            print(f"  {fname[:25]:<25} {quarter}  {count:>4} positions  ${aum:>6.1f}B")

    print(f"\n{'='*60}")
    print(f"✓ 13F collection complete: {total_holdings} holdings stored")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--filer', help='Filter by filer name')
    parser.add_argument('--backfill', type=int, default=2, help='Quarters to backfill')
    args = parser.parse_args()

    collect_13f_holdings(filer_name=args.filer, quarters=args.backfill)
