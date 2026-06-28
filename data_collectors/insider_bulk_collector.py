import os, sys, time
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.db import get_conn, refresh_log
from utils.logger import get_logger

log = get_logger(__name__)


def get_date_range(days=7):
    to_date = date.today()
    from_date = to_date - timedelta(days=days)
    return from_date.strftime('%d-%m-%Y'), to_date.strftime('%d-%m-%Y')


def get_stock_id_map():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT tradingsymbol, id FROM stocks")
    m = {row[0]: row[1] for row in cur.fetchall()}
    cur.close(); conn.close()
    return m


def collect_insider_trades(days=7):
    log.info("Source 1: Insider trades via pnsea...")
    from_date, to_date = get_date_range(days)
    try:
        from pnsea import NSE
        nse = NSE()
        df = nse.insider.insider_data(from_date=from_date, to_date=to_date)
    except Exception as e:
        log.warning(f"  pnsea insider fetch failed: {e}")
        return 0
    if df is None or df.empty:
        log.info(f"  No insider trades in last {days} days")
        return 0
    log.info(f"  Fetched {len(df)} insider trade records")
    stock_map = get_stock_id_map()
    conn = get_conn(); cur = conn.cursor(); stored = 0
    for _, row in df.iterrows():
        symbol = str(row.get('symbol', '')).upper().strip()
        stock_id = stock_map.get(symbol)
        try:
            trade_date = datetime.strptime(str(row.get('date', '')).strip()[:10], '%d-%m-%Y').date()
        except ValueError:
            trade_date = date.today()
        def safe_float(val):
            try:
                return float(str(val).replace(',', '').strip()) if val and str(val).strip() not in ('', '-', 'nan') else None
            except (ValueError, TypeError):
                return None
        try:
            cur.execute("""
                INSERT INTO insider_trades (stock_id, date, person_name, person_category, transaction, quantity, price, post_trade_pct, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'nse_pit') ON CONFLICT DO NOTHING
            """, (stock_id, trade_date, str(row.get('acqName', ''))[:200], str(row.get('personCategory', ''))[:100],
                str(row.get('tdpTransactionType', ''))[:50], safe_float(row.get('secAcq')),
                safe_float(row.get('secVal')), safe_float(row.get('afterAcqSharesPer'))))
            stored += 1
        except Exception as e:
            log.warning(f"  Insert failed: {e}")
    conn.commit(); cur.close(); conn.close()
    log.info(f"  Stored {stored} insider trade records")
    return stored


def collect_bulk_deals(days=7):
    log.info("Source 2: Bulk deals...")
    stored = 0
    stock_map = get_stock_id_map()
    conn = get_conn(); cur = conn.cursor()

    def safe_float(val):
        try:
            return float(str(val).replace(',', '').strip()) if val and str(val).strip() not in ('', '-', 'nan') else None
        except (ValueError, TypeError):
            return None

    def store_deals(records):
        count = 0
        for rec in records:
            symbol = str(rec.get('symbol', rec.get('Symbol', ''))).upper().strip()
            stock_id = stock_map.get(symbol)
            date_str = str(rec.get('date', rec.get('Date', ''))).strip()
            try:
                deal_date = datetime.strptime(date_str, '%d-%b-%Y').date()
            except ValueError:
                try:
                    deal_date = datetime.strptime(date_str, '%d-%m-%Y').date()
                except ValueError:
                    deal_date = date.today()
            try:
                cur.execute("""
                    INSERT INTO bulk_deals (stock_id, date, deal_type, client_name, transaction, quantity, price, source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'nse_bulk') ON CONFLICT DO NOTHING
                """, (stock_id, deal_date, 'bulk',
                    str(rec.get('clientName', rec.get('Client Name', '')))[:200],
                    str(rec.get('buySell', rec.get('Buy/Sell', '')))[:10],
                    safe_float(rec.get('qty', rec.get('Quantity Traded'))),
                    safe_float(rec.get('watp', rec.get('Trade Price / Wght. Avg. Price')))))
                count += 1
            except Exception as e:
                log.warning(f"  Bulk insert failed: {e}")
        return count

    try:
        from nsepython import get_bulkdeals
        df = get_bulkdeals()
        if df is not None and not df.empty:
            n = store_deals(df.to_dict('records'))
            stored += n
            log.info(f"  Today bulk deals: {n} stored")
    except Exception as e:
        log.warning(f"  nsepython bulk deals failed: {e}")

    if days > 1:
        try:
            import requests
            from_date, to_date = get_date_range(days)
            s = requests.Session()
            HEADERS = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json', 'Referer': 'https://www.nseindia.com'}
            s.get('https://www.nseindia.com', headers=HEADERS, timeout=10)
            time.sleep(2)
            resp = s.get(f'https://www.nseindia.com/api/snapshot-capital-market-largedeal?from={from_date}&to={to_date}&type=bulk_deals', headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                n = store_deals(resp.json().get('BULK_DEALS_DATA', []))
                stored += n
                log.info(f"  Historical bulk deals: {n} stored")
        except Exception as e:
            log.warning(f"  Historical bulk deals failed: {e}")

    conn.commit(); cur.close(); conn.close()
    return stored


def collect_block_deals(days=7):
    """
    Collect NSE block deals from snapshot-capital-market-largedeal API.
    Block deals = large negotiated trades executed in a dedicated window before market open.
    Stored in bulk_deals table with deal_type='block', source='nse_block'.
    """
    import requests
    log.info("Collecting block deals...")
    stock_map = get_stock_id_map()

    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'application/json',
        'Referer': 'https://www.nseindia.com/',
    }

    def safe_float(val):
        try:
            return float(str(val).replace(',', '').strip()) if val and str(val).strip() not in ('', '-', 'nan') else None
        except (ValueError, TypeError):
            return None

    conn = get_conn()
    cur = conn.cursor()

    # Ensure data_refresh_log entry exists
    cur.execute("""
        INSERT INTO data_refresh_log (source, tier, status, rows_upserted)
        VALUES ('block_deals', 'daily', 'never_run', 0)
        ON CONFLICT (source) DO NOTHING
    """)
    conn.commit()

    stored = 0
    try:
        from_date, to_date = get_date_range(days)
        s = requests.Session()
        s.get('https://www.nseindia.com', headers=HEADERS, timeout=10)
        time.sleep(1)

        url = (
            f'https://www.nseindia.com/api/snapshot-capital-market-largedeal'
            f'?from={from_date}&to={to_date}&type=block_deals'
        )
        resp = s.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            log.warning(f"Block deals API returned {resp.status_code}")
        else:
            records = resp.json().get('BLOCK_DEALS_DATA', [])
            log.info(f"  Block deals from API: {len(records)}")
            for rec in records:
                symbol = str(rec.get('symbol', '')).upper().strip()
                stock_id = stock_map.get(symbol)
                date_str = str(rec.get('date', '')).strip()
                try:
                    deal_date = datetime.strptime(date_str, '%d-%b-%Y').date()
                except ValueError:
                    deal_date = date.today()
                try:
                    cur.execute("""
                        INSERT INTO bulk_deals
                            (stock_id, date, deal_type, client_name, transaction, quantity, price, source)
                        VALUES (%s, %s, 'block', %s, %s, %s, %s, 'nse_block')
                        ON CONFLICT DO NOTHING
                    """, (
                        stock_id, deal_date,
                        str(rec.get('clientName', ''))[:200],
                        str(rec.get('buySell', ''))[:10],
                        safe_float(rec.get('qty')),
                        safe_float(rec.get('watp')),
                    ))
                    stored += 1
                except Exception as e:
                    log.warning(f"  Block deal insert failed for {symbol}: {e}")
    except Exception as e:
        log.warning(f"Block deals collection failed: {e}")

    conn.commit()
    cur.execute(
        "UPDATE data_refresh_log SET status='success', completed_at=NOW(), rows_upserted=%s WHERE source='block_deals'",
        (stored,)
    )
    conn.commit()
    cur.close()
    conn.close()
    log.info(f"  Block deals stored: {stored}")
    return stored


def print_summary():
    conn = get_conn(); cur = conn.cursor()
    print(f"\n{'='*65}\nINSIDER TRADES — last 7 days\n{'='*65}")
    cur.execute("""SELECT s.tradingsymbol, it.person_name, it.person_category, it.transaction, it.date
        FROM insider_trades it LEFT JOIN stocks s ON it.stock_id = s.id
        WHERE it.date >= CURRENT_DATE - INTERVAL '7 days' ORDER BY it.date DESC LIMIT 20""")
    rows = cur.fetchall()
    for sym, name, cat, txn, dt in rows:
        print(f"  {str(dt)[:10]}  {str(sym or 'UNK'):<12} {str(txn):<8} {str(cat)[:20]:<20} {str(name)[:30]}")
    if not rows: print("  No insider trades")
    print(f"\n{'='*65}\nBULK DEALS — last 7 days\n{'='*65}")
    cur.execute("""SELECT s.tradingsymbol, bd.client_name, bd.transaction, bd.date
        FROM bulk_deals bd LEFT JOIN stocks s ON bd.stock_id = s.id
        WHERE bd.date >= CURRENT_DATE - INTERVAL '7 days' ORDER BY bd.date DESC LIMIT 20""")
    rows = cur.fetchall()
    for sym, client, txn, dt in rows:
        print(f"  {str(dt)[:10]}  {str(sym or 'UNK'):<12} {str(txn):<6} {str(client)[:40]}")
    if not rows: print("  No bulk deals")
    print(f"{'='*65}\n")
    cur.close(); conn.close()


def collect_insider_and_bulk(days=7):
    log.info("=== Insider trades + Bulk deals collection starting ===")
    with refresh_log('insider_trades') as rlog:
        n1 = collect_insider_trades(days)
        n2 = collect_bulk_deals(days)
        rlog['rows'] = n1 + n2
    log.info(f"=== Complete — {n1} insider + {n2} bulk deals ===")
    print_summary()


if __name__ == '__main__':
    days = 7
    if '--days' in sys.argv:
        idx = sys.argv.index('--days')
        if idx + 1 < len(sys.argv):
            days = int(sys.argv[idx + 1])
    collect_insider_and_bulk(days=days)
