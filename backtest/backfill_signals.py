"""backtest/backfill_signals.py — historical signal_explanations backfill.

Phase 1 follow-up: signal_explanations only had live history going back to when the
nse_signals asset first ran (2026-07-02), which isn't enough for a meaningful
multi-year backtest. This loops signals.engine.run_signals(as_of=d) (Phase 0c) over
every trading day technical_indicators actually has data for, building up historical
signal_explanations rows for backtest/engine.py to trade against.

Idempotent — signal_explanations upserts on (stock_id, date, horizon), so this is safe
to re-run or resume after an interruption. skip_external is forced True: external
sentiment has no historical replay (see signals/engine.py's is_live check), and
run_signals() already skips it for a past as_of regardless.
"""
import time
from datetime import date

from signals.engine import run_signals
from signals.util import get_conn


def get_trading_days(start: date | None = None, end: date | None = None) -> list[date]:
    """Every date technical_indicators has data for — i.e. every day the pipeline actually
    computed indicators, so we never waste a call on a non-trading day."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            conds, params = [], []
            if start:
                conds.append("date >= %s")
                params.append(start)
            if end:
                conds.append("date <= %s")
                params.append(end)
            where = f"WHERE {' AND '.join(conds)}" if conds else ""
            cur.execute(f"SELECT DISTINCT date FROM technical_indicators {where} ORDER BY date", params)
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def backfill(start: date | None = None, end: date | None = None, watchlist: str = "Default") -> dict:
    days = get_trading_days(start, end)
    if not days:
        print("No trading days found in range")
        return {"days": 0}

    print(f"Backfilling {len(days)} trading days ({days[0]} -> {days[-1]})")
    t0 = time.time()
    for i, d in enumerate(days):
        result = run_signals(as_of=d, watchlist=watchlist, skip_external=True, external_pause=0)
        if (i + 1) % 25 == 0 or i == len(days) - 1:
            elapsed = time.time() - t0
            print(f"  [{i + 1}/{len(days)}] {d} — {result['stocks']} stocks — {elapsed:.1f}s elapsed")
    elapsed = time.time() - t0
    print(f"Done: {len(days)} days in {elapsed:.1f}s")
    return {"days": len(days), "elapsed_s": round(elapsed, 1)}


if __name__ == "__main__":
    backfill()
