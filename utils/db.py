import os, psycopg2, psycopg2.extras
from contextlib import contextmanager
from datetime import datetime
from utils.logger import db_logger as log

_DB = os.environ.get("DATABASE_URL", "postgresql://puneetgrover@localhost/stock_analyzer")

def get_conn():
    return psycopg2.connect(_DB)

@contextmanager
def refresh_log(source):
    """Context manager wrapping a collector run. Collectors set:
        meta['rows']      — actual rows written (required)
        meta['expected']  — expected rows (optional; enables coverage_pct + 'partial')
        meta['gaps']      — list of failed stock_ids/dates (optional)
    On exit it records actual/expected/coverage and status (success | partial)."""
    import json as _json
    meta = {"rows": 0}
    log.info(f"[{source}] Starting")
    conn = get_conn(); cur = conn.cursor()
    cur.execute("UPDATE data_refresh_log SET status='running', started_at=%s, error_message=NULL WHERE source=%s", (datetime.now(), source))
    conn.commit(); cur.close(); conn.close()
    try:
        yield meta
        actual = meta.get("rows", 0)
        expected = meta.get("expected")
        gaps = meta.get("gaps")
        coverage = round(100.0 * actual / expected, 1) if expected else None
        status = "partial" if (expected and actual < expected) else "success"
        conn = get_conn(); cur = conn.cursor()
        cur.execute(
            "UPDATE data_refresh_log SET status=%s, completed_at=%s, rows_upserted=%s, "
            "actual_rows=%s, expected_rows=%s, coverage_pct=%s, gaps_detected=%s WHERE source=%s",
            (status, datetime.now(), actual, actual, expected, coverage,
             _json.dumps(gaps) if gaps else None, source))
        conn.commit(); cur.close(); conn.close()
        log.info(f"[{source}] Done ({status}, {actual}/{expected if expected else '?'} rows)")
    except Exception as e:
        log.error(f"[{source}] Failed: {e}", exc_info=True)
        conn = get_conn(); cur = conn.cursor()
        cur.execute("UPDATE data_refresh_log SET status='error', completed_at=%s, error_message=%s WHERE source=%s", (datetime.now(), str(e)[:500], source))
        conn.commit(); cur.close(); conn.close()
        raise

def get_watchlist_stocks(watchlist_name="Default"):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT s.id, s.instrument_token, s.tradingsymbol, s.name FROM watchlist w JOIN stocks s ON w.stock_id=s.id WHERE w.name=%s ORDER BY s.tradingsymbol", (watchlist_name,))
    rows = cur.fetchall(); cur.close(); conn.close()
    return rows

def get_stock_id_map(watchlist_name="Default"):
    return {sym: sid for sid, _, sym, _ in get_watchlist_stocks(watchlist_name)}

def get_refresh_status():
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT source, tier, status, completed_at, rows_upserted, error_message FROM data_refresh_log ORDER BY tier, source")
    rows = [dict(r) for r in cur.fetchall()]; cur.close(); conn.close()
    return rows

def needs_refresh(source, min_hours):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT completed_at, status FROM data_refresh_log WHERE source=%s", (source,))
    row = cur.fetchone(); cur.close(); conn.close()
    if not row or row[1] != "success" or row[0] is None: return True
    return (datetime.now() - row[0]).total_seconds() / 3600 >= min_hours
