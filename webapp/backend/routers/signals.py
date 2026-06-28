"""Signal dashboard — BUY/SELL/WATCH across the watchlist with price, RSI, MACD."""
from fastapi import APIRouter

from db import query_all
from signals_engine import signal_for_stock

router = APIRouter(prefix="/api/signals", tags=["signals"])

_WATCHLIST_SQL = """
    SELECT s.id, s.tradingsymbol, s.name, s.exchange
    FROM watchlist w JOIN stocks s ON w.stock_id = s.id
    WHERE w.name = %s
    ORDER BY s.tradingsymbol
"""


@router.get("")
def list_signals(watchlist: str = "Default", verdict: str | None = None):
    """One row per watchlist stock with its computed verdict + indicators."""
    stocks = query_all(_WATCHLIST_SQL, (watchlist,))
    out = []
    for s in stocks:
        sig = signal_for_stock(s["id"])
        if not sig:
            continue
        row = {"stock_id": s["id"], "symbol": s["tradingsymbol"],
               "name": s["name"], "exchange": s["exchange"], **sig}
        if verdict and row["verdict"] != verdict.upper():
            continue
        out.append(row)
    # BUY first, then SELL, WATCH, NEUTRAL; strong signals bubble up within group.
    order = {"BUY": 0, "SELL": 1, "WATCH": 2, "NEUTRAL": 3}
    out.sort(key=lambda r: (order.get(r["verdict"], 9), -(r["rsi_14"] or 0)))
    counts = {"BUY": 0, "SELL": 0, "WATCH": 0, "NEUTRAL": 0}
    for r in out:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    return {"signals": out, "counts": counts}
