"""Signal dashboard — legacy verdict + 4-pillar explainable engine (Session L)."""
from fastapi import APIRouter, HTTPException

from db import query_all, query_one
from signals_engine import signal_for_stock

router = APIRouter(prefix="/api/signals", tags=["signals"])

_HORIZONS = ("SHORT", "MID", "LONG")


@router.get("/explained")
def explained(watchlist: str = "Default"):
    """Per watchlist stock: pillar scores (horizon-independent) + per-horizon overall
    signal/confidence/agreement, from the latest signal_explanations run."""
    rows = query_all(
        """
        SELECT se.stock_id, se.horizon, se.signal_type, se.overall_score, se.confidence,
               se.all_pillars_agree, se.technical_score, se.fundamental_score,
               se.flow_score, se.external_score,
               s.tradingsymbol AS symbol, s.name, s.exchange, s.industry
        FROM signal_explanations se
        JOIN stocks s ON s.id = se.stock_id
        JOIN watchlist w ON w.stock_id = se.stock_id AND w.name = %s
        WHERE se.date = (SELECT MAX(date) FROM signal_explanations)
        """,
        (watchlist,),
    )
    by_stock: dict = {}
    for r in rows:
        sid = r["stock_id"]
        e = by_stock.setdefault(sid, {
            "stock_id": sid, "symbol": r["symbol"], "name": r["name"],
            "exchange": r["exchange"], "industry": r["industry"],
            "technical_score": r["technical_score"], "fundamental_score": r["fundamental_score"],
            "flow_score": r["flow_score"], "external_score": r["external_score"],
            "horizons": {},
        })
        e["horizons"][r["horizon"]] = {
            "signal_type": r["signal_type"], "overall_score": r["overall_score"],
            "confidence": r["confidence"], "all_pillars_agree": r["all_pillars_agree"],
        }
    return {"stocks": list(by_stock.values())}


@router.get("/explanation/{stock_id}")
def explanation(stock_id: int, horizon: str = "SHORT"):
    """Full explanation for one stock + horizon (all pillar reasoning, contrary, what-would-change)."""
    horizon = horizon.upper()
    if horizon not in _HORIZONS:
        raise HTTPException(400, "horizon must be SHORT/MID/LONG")
    row = query_one(
        """
        SELECT se.*, s.tradingsymbol AS symbol, s.name, s.exchange, s.industry
        FROM signal_explanations se JOIN stocks s ON s.id = se.stock_id
        WHERE se.stock_id = %s AND se.horizon = %s
          AND se.date = (SELECT MAX(date) FROM signal_explanations WHERE stock_id = %s)
        """,
        (stock_id, horizon, stock_id),
    )
    if not row:
        raise HTTPException(404, "No signal explanation computed for this stock yet")
    return row

_WATCHLIST_SQL = """
    SELECT s.id, s.tradingsymbol, s.name, s.exchange, s.sector, s.industry,
           sc.data_completeness_score
    FROM watchlist w JOIN stocks s ON w.stock_id = s.id
    LEFT JOIN LATERAL (
        SELECT data_completeness_score FROM stock_scores
        WHERE stock_id = s.id ORDER BY date DESC LIMIT 1
    ) sc ON true
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
               "name": s["name"], "exchange": s["exchange"],
               "sector": s.get("sector"), "industry": s.get("industry"),
               "completeness": s.get("data_completeness_score"), **sig}
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
