"""Portfolio — private, localhost-only, TOTP-gated holdings.

Hard rules (enforced here + by portfolio_localhost_guard middleware + portfolio_auth):
  - Accessible from localhost only (ngrok/external → 403 in middleware).
  - Requires main session (global auth middleware) AND a fresh portfolio TOTP session.
  - Sensitive columns (quantity, prices, targets) encrypted at rest (pgcrypto).
  - unrealized P&L / current value are NEVER stored — always computed from daily_prices.
  - Nothing financial ever leaves the box: Telegram alerts carry symbol + alert type only.
"""
import io
from datetime import date, datetime

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, File
from pydantic import BaseModel

from portfolio_db import portfolio_cursor, audit, ENCRYPTION_KEY
from portfolio_auth import (
    verify_totp, issue_portfolio_token, require_portfolio, is_localhost,
    portfolio_session_valid, PORTFOLIO_COOKIE, PORTFOLIO_TTL_SECONDS,
)

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

EXPECTED_COLS = ["symbol", "exchange", "quantity", "buying_price",
                 "buying_date", "target_price", "stop_loss", "notes"]


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# ── TOTP session ──────────────────────────────────────────────────────────────
class TotpBody(BaseModel):
    code: str


@router.post("/verify-totp")
def verify_totp_endpoint(body: TotpBody, request: Request, response: Response):
    """Verify a 6-digit TOTP; on success issue a 15-min portfolio_session cookie.

    localhost is enforced by middleware; main session by the global auth middleware.
    """
    if not is_localhost(request):
        raise HTTPException(403, "Portfolio is accessible from localhost only")
    if not verify_totp(body.code):
        audit("totp_failure", _ip(request))
        raise HTTPException(401, "Invalid TOTP code")
    token = issue_portfolio_token()
    response.set_cookie(
        key=PORTFOLIO_COOKIE, value=token, max_age=PORTFOLIO_TTL_SECONDS,
        httponly=True, samesite="lax", secure=request.url.scheme == "https",
    )
    audit("totp_success", _ip(request))
    return {"status": "ok", "expires_in": PORTFOLIO_TTL_SECONDS}


@router.get("/status")
def portfolio_status(request: Request):
    """Frontend gate/countdown: is a portfolio session active and for how long?
    Requires localhost + main session (global), but NOT an existing TOTP session."""
    if not is_localhost(request):
        raise HTTPException(403, "Portfolio is accessible from localhost only")
    return {"verified": portfolio_session_valid(request), "ttl_seconds": PORTFOLIO_TTL_SECONDS}


@router.post("/logout-totp")
def logout_totp(request: Request, response: Response):
    response.delete_cookie(PORTFOLIO_COOKIE)
    audit("totp_logout", _ip(request))
    return {"status": "ok"}


# ── Symbol resolution / prices (read-only public market data) ─────────────────
def _resolve_stock(cur, symbol: str, exchange: str | None):
    """Return (stock_id, current_price) for a symbol, or (None, None) if unknown."""
    if exchange:
        cur.execute(
            "SELECT id FROM stocks WHERE UPPER(tradingsymbol)=UPPER(%s) AND UPPER(exchange)=UPPER(%s) LIMIT 1",
            (symbol, exchange),
        )
    else:
        cur.execute("SELECT id FROM stocks WHERE UPPER(tradingsymbol)=UPPER(%s) LIMIT 1", (symbol,))
    row = cur.fetchone()
    if not row:
        return None, None
    sid = row["id"]
    cur.execute(
        "SELECT close FROM daily_prices WHERE stock_id=%s ORDER BY date DESC LIMIT 1", (sid,)
    )
    pr = cur.fetchone()
    return sid, (float(pr["close"]) if pr and pr["close"] is not None else None)


# ── Upload: preview then save ─────────────────────────────────────────────────
def _parse_upload(raw: bytes, filename: str) -> pd.DataFrame:
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(raw))
    else:
        df = pd.read_csv(io.BytesIO(raw))
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df


def _row_to_record(r: dict) -> dict:
    def g(k):
        v = r.get(k)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        return v
    return {
        "symbol": str(g("symbol") or "").strip().upper(),
        "exchange": (str(g("exchange")).strip().upper() if g("exchange") else None),
        "quantity": g("quantity"),
        "buying_price": g("buying_price"),
        "buying_date": (str(g("buying_date"))[:10] if g("buying_date") else None),
        "target_price": g("target_price"),
        "stop_loss": g("stop_loss"),
        "notes": (str(g("notes")) if g("notes") else None),
    }


def _validate(rec: dict, cur) -> str | None:
    if not rec["symbol"]:
        return "missing symbol"
    try:
        if rec["quantity"] is None or float(rec["quantity"]) <= 0:
            return "quantity must be > 0"
        if rec["buying_price"] is None or float(rec["buying_price"]) <= 0:
            return "buying_price must be > 0"
        for f in ("target_price", "stop_loss"):
            if rec[f] is not None and rec[f] != "":
                float(rec[f])
    except (ValueError, TypeError):
        return "non-numeric price/quantity"
    sid, _ = _resolve_stock(cur, rec["symbol"], rec["exchange"])
    if sid is None:
        return f"symbol '{rec['symbol']}' not found in stocks universe"
    return None


@router.post("/preview")
async def preview(request: Request, file: UploadFile = File(...), _=Depends(require_portfolio)):
    """Parse an uploaded CSV/Excel and validate rows against the stocks universe. No save."""
    raw = await file.read()
    try:
        df = _parse_upload(raw, file.filename)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Could not parse file: {e}")
    missing = [c for c in ("symbol", "quantity", "buying_price") if c not in df.columns]
    if missing:
        raise HTTPException(400, f"Missing required columns: {', '.join(missing)}")

    rows = []
    with portfolio_cursor() as cur:
        for _, raw_row in df.iterrows():
            rec = _row_to_record(raw_row.to_dict())
            err = _validate(rec, cur)
            rows.append({**rec, "valid": err is None, "error": err})
    audit("preview", _ip(request), f"rows={len(rows)}")
    return {"rows": rows, "valid_count": sum(1 for r in rows if r["valid"]), "total": len(rows)}


class SaveBody(BaseModel):
    rows: list[dict]
    replace: bool = False  # if true, clear existing holdings first


@router.post("/save")
def save(body: SaveBody, request: Request, _=Depends(require_portfolio)):
    """Persist validated holdings (encrypting sensitive fields). Re-validates server-side."""
    if not ENCRYPTION_KEY:
        raise HTTPException(500, "PORTFOLIO_ENCRYPTION_KEY not configured")
    saved, skipped = 0, []
    with portfolio_cursor(commit=True) as cur:
        if body.replace:
            cur.execute("DELETE FROM portfolio.holdings")
        for raw_row in body.rows:
            rec = _row_to_record({k: raw_row.get(k) for k in EXPECTED_COLS})
            err = _validate(rec, cur)
            if err:
                skipped.append({"symbol": rec.get("symbol"), "error": err})
                continue
            cur.execute(
                """
                INSERT INTO portfolio.holdings
                    (symbol, exchange, quantity, buying_price, buying_date, target_price, stop_loss, notes)
                VALUES (%s, %s,
                        pgp_sym_encrypt(%s, %s), pgp_sym_encrypt(%s, %s), %s,
                        CASE WHEN %s IS NULL THEN NULL ELSE pgp_sym_encrypt(%s, %s) END,
                        CASE WHEN %s IS NULL THEN NULL ELSE pgp_sym_encrypt(%s, %s) END,
                        %s)
                """,
                (
                    rec["symbol"], rec["exchange"],
                    str(rec["quantity"]), ENCRYPTION_KEY,
                    str(rec["buying_price"]), ENCRYPTION_KEY,
                    rec["buying_date"],
                    (str(rec["target_price"]) if rec["target_price"] not in (None, "") else None),
                    str(rec["target_price"]), ENCRYPTION_KEY,
                    (str(rec["stop_loss"]) if rec["stop_loss"] not in (None, "") else None),
                    str(rec["stop_loss"]), ENCRYPTION_KEY,
                    rec["notes"],
                ),
            )
            saved += 1
    audit("upload_save", _ip(request), f"saved={saved} skipped={len(skipped)}")
    return {"saved": saved, "skipped": skipped}


# ── Read holdings (decrypt + compute, never store P&L) ────────────────────────
def _load_holdings(cur) -> list[dict]:
    cur.execute(
        f"""
        SELECT id, symbol, exchange,
               pgp_sym_decrypt(quantity, %s)::numeric      AS quantity,
               pgp_sym_decrypt(buying_price, %s)::numeric  AS buying_price,
               buying_date,
               CASE WHEN target_price IS NULL THEN NULL ELSE pgp_sym_decrypt(target_price, %s)::numeric END AS target_price,
               CASE WHEN stop_loss    IS NULL THEN NULL ELSE pgp_sym_decrypt(stop_loss, %s)::numeric END    AS stop_loss,
               notes, created_at, updated_at
        FROM portfolio.holdings ORDER BY symbol
        """,
        (ENCRYPTION_KEY, ENCRYPTION_KEY, ENCRYPTION_KEY, ENCRYPTION_KEY),
    )
    out = []
    for h in cur.fetchall():
        _, current = _resolve_stock(cur, h["symbol"], h["exchange"])
        qty = float(h["quantity"]) if h["quantity"] is not None else 0.0
        bp = float(h["buying_price"]) if h["buying_price"] is not None else 0.0
        tp = float(h["target_price"]) if h["target_price"] is not None else None
        sl = float(h["stop_loss"]) if h["stop_loss"] is not None else None
        # computed fresh — NEVER stored
        pnl = (current - bp) * qty if current is not None else None
        pnl_pct = ((current / bp - 1) * 100) if (current is not None and bp) else None
        out.append({
            "id": h["id"], "symbol": h["symbol"], "exchange": h["exchange"],
            "quantity": qty, "buying_price": bp, "buying_date": h["buying_date"],
            "target_price": tp, "stop_loss": sl, "notes": h["notes"],
            "current_price": current,
            "invested": round(bp * qty, 2),
            "current_value": (round(current * qty, 2) if current is not None else None),
            "unrealized_pnl": (round(pnl, 2) if pnl is not None else None),
            "pnl_pct": (round(pnl_pct, 2) if pnl_pct is not None else None),
        })
    return out


@router.get("/holdings")
def holdings(request: Request, _=Depends(require_portfolio)):
    with portfolio_cursor() as cur:
        data = _load_holdings(cur)
    audit("view_holdings", _ip(request), f"count={len(data)}")
    return {"holdings": data}


class HoldingUpdate(BaseModel):
    quantity: float | None = None
    buying_price: float | None = None
    buying_date: str | None = None
    target_price: float | None = None
    stop_loss: float | None = None
    notes: str | None = None


@router.put("/holding/{holding_id}")
def update_holding(holding_id: int, body: HoldingUpdate, request: Request, _=Depends(require_portfolio)):
    sets, params = [], []
    enc = {"quantity", "buying_price", "target_price", "stop_loss"}
    for field in ("quantity", "buying_price", "buying_date", "target_price", "stop_loss", "notes"):
        val = getattr(body, field)
        if val is None:
            continue
        if field in enc:
            sets.append(f"{field} = pgp_sym_encrypt(%s, %s)")
            params.extend([str(val), ENCRYPTION_KEY])
        else:
            sets.append(f"{field} = %s")
            params.append(val)
    if not sets:
        raise HTTPException(400, "No fields to update")
    sets.append("updated_at = now()")
    params.append(holding_id)
    with portfolio_cursor(commit=True) as cur:
        cur.execute(f"UPDATE portfolio.holdings SET {', '.join(sets)} WHERE id = %s RETURNING id", params)
        if not cur.fetchone():
            raise HTTPException(404, "Holding not found")
    audit("update_holding", _ip(request), f"id={holding_id}")
    return {"status": "updated"}


@router.delete("/holding/{holding_id}")
def delete_holding(holding_id: int, request: Request, _=Depends(require_portfolio)):
    with portfolio_cursor(commit=True) as cur:
        cur.execute("DELETE FROM portfolio.holdings WHERE id = %s RETURNING id", (holding_id,))
        if not cur.fetchone():
            raise HTTPException(404, "Holding not found")
    audit("delete_holding", _ip(request), f"id={holding_id}")
    return {"status": "deleted"}


@router.get("/summary")
def summary(request: Request, _=Depends(require_portfolio)):
    """Aggregate stats — computed on the fly, never stored."""
    with portfolio_cursor() as cur:
        data = _load_holdings(cur)
    invested = sum(h["invested"] for h in data if h["invested"] is not None)
    cur_val = sum(h["current_value"] for h in data if h["current_value"] is not None)
    pnl = sum(h["unrealized_pnl"] for h in data if h["unrealized_pnl"] is not None)
    audit("view_summary", _ip(request), f"count={len(data)}")
    return {
        "holdings_count": len(data),
        "invested": round(invested, 2),
        "current_value": round(cur_val, 2),
        "unrealized_pnl": round(pnl, 2),
        "pnl_pct": round((cur_val / invested - 1) * 100, 2) if invested else None,
    }


# ── Alerts (computed locally; Telegram gets type+direction only) ──────────────
def _compute_alerts(cur) -> list[dict]:
    holds = _load_holdings(cur)
    alerts: list[dict] = []
    for h in holds:
        cur_p, sl, tp, sym = h["current_price"], h["stop_loss"], h["target_price"], h["symbol"]
        if cur_p is None:
            continue
        if sl is not None and cur_p < sl:
            alerts.append({"symbol": sym, "type": "STOP_LOSS_BREACH", "severity": "CRITICAL",
                           "message": f"{sym} below stop-loss zone"})
        elif sl is not None and cur_p < sl * 1.03:
            alerts.append({"symbol": sym, "type": "APPROACHING_STOP", "severity": "HIGH",
                           "message": f"{sym} approaching stop-loss zone"})
        if tp is not None and cur_p >= tp:
            alerts.append({"symbol": sym, "type": "TARGET_REACHED", "severity": "INFO",
                           "message": f"{sym} reached target zone"})
        # large single-day drop
        cur.execute(
            "SELECT close FROM daily_prices dp JOIN stocks s ON s.id=dp.stock_id "
            "WHERE UPPER(s.tradingsymbol)=UPPER(%s) ORDER BY dp.date DESC LIMIT 2", (sym,))
        px = cur.fetchall()
        if len(px) == 2 and px[1]["close"]:
            chg = (float(px[0]["close"]) / float(px[1]["close"]) - 1) * 100
            if chg <= -5:
                alerts.append({"symbol": sym, "type": "LARGE_DROP", "severity": "HIGH",
                               "message": f"{sym} down sharply today"})
        # earnings in next 7 days
        cur.execute(
            "SELECT 1 FROM earnings_calendar ec JOIN stocks s ON s.id=ec.stock_id "
            "WHERE UPPER(s.tradingsymbol)=UPPER(%s) AND ec.results_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 7 LIMIT 1",
            (sym,))
        if cur.fetchone():
            alerts.append({"symbol": sym, "type": "EARNINGS_SOON", "severity": "INFO",
                           "message": f"{sym} earnings within 7 days"})
        # insider selling (30d)
        cur.execute(
            "SELECT COUNT(*) AS n FROM insider_trades it JOIN stocks s ON s.id=it.stock_id "
            "WHERE UPPER(s.tradingsymbol)=UPPER(%s) AND it.transaction='SELL' AND it.date >= CURRENT_DATE - 30",
            (sym,))
        r = cur.fetchone()
        if r and (r["n"] or 0) >= 2:
            alerts.append({"symbol": sym, "type": "INSIDER_SELLING", "severity": "MEDIUM",
                           "message": f"{sym} recent insider selling"})
        # pledging
        cur.execute(
            "SELECT 1 FROM pledging_alerts pa JOIN stocks s ON s.id=pa.stock_id "
            "WHERE UPPER(s.tradingsymbol)=UPPER(%s) LIMIT 1", (sym,))
        if cur.fetchone():
            alerts.append({"symbol": sym, "type": "PLEDGING", "severity": "MEDIUM",
                           "message": f"{sym} has promoter pledging"})
    # market-wide FII selling streak (once, if any India holding)
    if any((h["exchange"] or "") in ("NSE", "BSE") for h in holds):
        cur.execute("SELECT fii_net FROM fii_dii_flows ORDER BY date DESC LIMIT 10")
        streak = 0
        for row in cur.fetchall():
            if row["fii_net"] is not None and float(row["fii_net"]) < 0:
                streak += 1
            else:
                break
        if streak >= 3:
            alerts.append({"symbol": "MARKET", "type": "FII_SELLING_STREAK", "severity": "MEDIUM",
                           "message": f"FII net selling {streak} days straight"})
    return alerts


@router.get("/alerts")
def alerts(request: Request, notify: bool = False, _=Depends(require_portfolio)):
    with portfolio_cursor() as cur:
        data = _compute_alerts(cur)
    audit("view_alerts", _ip(request), f"count={len(data)}")
    if notify:
        _notify_telegram(data)
        audit("telegram_alert", _ip(request), f"count={len(data)}")
    return {"alerts": data}


@router.get("/signal-overlay")
def signal_overlay(request: Request, _=Depends(require_portfolio)):
    """For the Signals dashboard 💼 overlay (localhost only): which watchlist stocks are
    held, and how far current price sits from stop-loss / target. No P&L, no quantities."""
    with portfolio_cursor() as cur:
        data = _load_holdings(cur)
    overlay = {}
    for h in data:
        cur_p, sl, tp = h["current_price"], h["stop_loss"], h["target_price"]
        overlay[h["symbol"]] = {
            "held": True,
            "stop_loss_dist_pct": (round((cur_p / sl - 1) * 100, 1) if (cur_p and sl) else None),
            "target_dist_pct": (round((tp / cur_p - 1) * 100, 1) if (cur_p and tp) else None),
        }
    return {"overlay": overlay}


def _notify_telegram(alerts_list: list[dict]) -> None:
    """Send SANITIZED alerts to Telegram — symbol + alert type only. NEVER quantities,
    prices, or P&L. Runs from localhost only (this endpoint is localhost-gated)."""
    import os
    import requests
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat or not alerts_list:
        return
    icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "INFO": "🔵"}
    # message contains ONLY the pre-sanitized `message` strings (no financials)
    lines = ["📋 Portfolio alerts:"] + [f"{icon.get(a['severity'], '•')} {a['message']}" for a in alerts_list]
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": "\n".join(lines[:20])}, timeout=10,
        )
    except Exception:
        pass
