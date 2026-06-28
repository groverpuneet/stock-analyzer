"""Database access for the web API.

Thin psycopg2 wrapper. Every request gets a short-lived connection and a
RealDictCursor so rows come back as plain dicts (JSON-friendly). Read-only by
design — the web layer never writes market data, only the watchlist table.
"""
import os
from contextlib import contextmanager
from decimal import Decimal

import psycopg2
import psycopg2.extras


def _clean(value):
    """Postgres numeric can hold NaN/Infinity, which are not valid JSON. Null them."""
    if isinstance(value, Decimal):
        if value.is_nan() or value.is_infinite():
            return None
    return value


def _clean_row(row: dict) -> dict:
    return {k: _clean(v) for k, v in row.items()}

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://puneetgrover@localhost/stock_analyzer"
)


@contextmanager
def get_cursor(commit: bool = False):
    """Yield a RealDictCursor. Commits only when explicitly asked (watchlist writes)."""
    conn = psycopg2.connect(DATABASE_URL)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query_all(sql: str, params: tuple = ()) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(sql, params)
        return [_clean_row(dict(r)) for r in cur.fetchall()]


def query_one(sql: str, params: tuple = ()) -> dict | None:
    with get_cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return _clean_row(dict(row)) if row else None
