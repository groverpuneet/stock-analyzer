"""Portfolio data layer — isolated connection + encryption + audit.

All portfolio DB access goes through `portfolio_user` (PORTFOLIO_DATABASE_URL), a role
with rights ONLY on the `portfolio` schema (+ read-only market data). Sensitive numeric
columns are encrypted with pgcrypto (pgp_sym_encrypt); the key (PORTFOLIO_ENCRYPTION_KEY)
lives only in the environment and is passed as a bind parameter at query time — never
written to the database, never logged.
"""
import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

# portfolio_user — schema-scoped role. DSN (with its password) comes ONLY from the
# environment (.env → PORTFOLIO_DATABASE_URL); never hardcode the credential here.
PORTFOLIO_DATABASE_URL = os.environ.get("PORTFOLIO_DATABASE_URL", "")
ENCRYPTION_KEY = os.environ.get("PORTFOLIO_ENCRYPTION_KEY", "")


@contextmanager
def portfolio_cursor(commit: bool = False):
    conn = psycopg2.connect(PORTFOLIO_DATABASE_URL)
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


def audit(action: str, ip_address: str | None, details: str | None = None) -> None:
    """Append an audit row. NEVER pass financial values in `details`."""
    try:
        with portfolio_cursor(commit=True) as cur:
            cur.execute(
                "INSERT INTO portfolio.audit_log (action, ip_address, details) VALUES (%s, %s, %s)",
                (action[:60], (ip_address or "")[:64], (details or "")[:500]),
            )
    except Exception:
        # Auditing must never break the request path (and must never surface financial data).
        pass
