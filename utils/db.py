import os
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from datetime import datetime
from utils.logger import db_logger as log

_DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://puneetgrover@localhost/stock_analyzer")

def get_conn():
    return psycopg2.connect(_DATABASE_URL)

@contextmanager
def refresh_log(source: str):
    meta = {"rows": 0}
    log.info(f"[{source}] Starting refresh")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE data_refresh_log SET status='running', started_at=%s, error_message=NULL WHERE source=%s", (datetime.now(), source))
    conn.commit(); cur.close(); conn.close()
    try:
        yield meta
        conn = get_conn(); cur = conn.cursor()
        cur.execute("UPDATE data_refresh_log SET status='success', completed_at=%s, rows_upserted=%s WHERE source=%s", (datetime.now(), meta.get("rows", 0), source))
        conn.commit(); cur.close(); conn.close()
        log.info(f"[{source}] Completed — {meta.get('rows', 0)} rows")
    except Exception as e:
        log.error(f"[{source}] Failed: {e}", exc_info=True)
        conn = get_conn(); cur = conn.cursor()
        cur.execute("UPDATE data_refresh_log SET status='error', completed_at=%s, error_message=%s WHERE source=%s", (datetime.now(), str(e)[:500], source))
        conn.commit(); cur.close(); conn.close()
        raise

def get_watchlist_stocks(watchlist_name="Default"):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""SELECT s.id, s.instrument_token, s.tradingsymbol, s.name
        FROM watchlist w JOIN stocks s ON w.stock_id = s.id
        WHERE w.name = %s ORDER BY s.tradingsymbol""", (watchlist_name,))
    rows = cur.fetchall(); cur.close(); conn.close()
    return rows

def get_stock_id_map(watchlist_name="Default"):
    return {sym: sid for sid, _, sym, _ in get_watchlist_stocks(watchlist_name)}

def get_refresh_status():
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT source, tier, status, completed_at, rows_upserted, error_message FROM data_refresh_log ORDER BY tier, source")
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return rows

def needs_refresh(source: str, min_hours: float) -> bool:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT completed_at, status FROM data_refresh_log WHERE source=%s", (source,))
    row = cur.fetchone(); cur.close(); conn.close()
    if not row or row[1] != "success" or row[0] is None:
        return True
    return (datetime.now() - row[0]).total_seconds() / 3600 >= min_hours
