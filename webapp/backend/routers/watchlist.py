"""Watchlist manager — named lists of symbols to track (not a portfolio).

Stores only the symbols a user wants to follow. No holdings, quantity, cost,
or P&L — purely a tracking list against public market data.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import query_all, query_one, get_cursor
from signals_engine import signal_for_stock

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class WatchlistAdd(BaseModel):
    stock_id: int
    name: str = "Default"
    notes: str | None = None


@router.get("/names")
def names():
    rows = query_all("SELECT DISTINCT name FROM watchlist ORDER BY name")
    return [r["name"] for r in rows]


@router.get("")
def list_watchlist(name: str = "Default", with_signals: bool = True):
    entries = query_all(
        """
        SELECT w.id AS entry_id, w.notes, w.created_at,
               s.id AS stock_id, s.tradingsymbol AS symbol, s.name, s.exchange
        FROM watchlist w JOIN stocks s ON w.stock_id = s.id
        WHERE w.name = %s ORDER BY s.tradingsymbol
        """,
        (name,),
    )
    if with_signals:
        for e in entries:
            sig = signal_for_stock(e["stock_id"])
            e["close"] = sig["close"] if sig else None
            e["rsi_14"] = sig["rsi_14"] if sig else None
            e["verdict"] = sig["verdict"] if sig else "NEUTRAL"
    return entries


@router.post("")
def add(item: WatchlistAdd):
    stock = query_one("SELECT id FROM stocks WHERE id = %s", (item.stock_id,))
    if not stock:
        raise HTTPException(404, "Stock not found")
    existing = query_one(
        "SELECT id FROM watchlist WHERE stock_id = %s AND name = %s",
        (item.stock_id, item.name),
    )
    if existing:
        raise HTTPException(409, "Already in this watchlist")
    with get_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO watchlist (stock_id, name, notes) VALUES (%s, %s, %s) RETURNING id",
            (item.stock_id, item.name, item.notes),
        )
        new_id = cur.fetchone()["id"]
    return {"id": new_id, "status": "added"}


@router.delete("/{entry_id}")
def remove(entry_id: int):
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM watchlist WHERE id = %s RETURNING id", (entry_id,))
        if not cur.fetchone():
            raise HTTPException(404, "Entry not found")
    return {"status": "removed"}
