"""Claude analysis chat — SSE streaming, token-optimized.

Token optimization: we never dump the database into the prompt. The context
builder pulls only the rows relevant to the question (the focused stock's latest
price/indicators/signal/news/fundamentals, plus a compact market + macro
snapshot) and passes those as a single context block. Stable instructions live
in the system prompt; only the per-question data varies.

Model: claude-opus-4-8 (Anthropic's most capable Opus-tier model). Streaming is
required for responsiveness and to avoid request timeouts.

Ground rule: this assistant only ever sees public market data. No portfolio,
holdings, P&L, or positions are queried or exposed.
"""
import os
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from db import query_all, query_one
from signals_engine import signal_for_stock

router = APIRouter(prefix="/api/chat", tags=["chat"])

MODEL = "claude-opus-4-8"

SYSTEM_PROMPT = (
    "You are a quantitative equity analyst embedded in a stock-analysis dashboard "
    "for Indian markets (NSE). Answer the user's question using ONLY the DATA CONTEXT "
    "provided with each message — it contains the latest figures from the user's "
    "PostgreSQL database. Be concise and specific; cite the numbers you use. If the "
    "context lacks what's needed, say so plainly rather than guessing. Never give "
    "personalised financial advice or position sizing; you analyse public market data only."
)


class ChatRequest(BaseModel):
    message: str
    stock_id: int | None = None
    history: list[dict] | None = None  # [{role, content}, ...]


def _build_context(message: str, stock_id: int | None) -> str:
    """Gather only the rows relevant to this question — keep it compact."""
    parts: list[str] = []

    # Market + macro snapshot (always small, always useful)
    fii = query_one(
        "SELECT date, fii_net, dii_net FROM fii_dii_flows ORDER BY date DESC LIMIT 1"
    )
    macro = query_all(
        """
        SELECT DISTINCT ON (indicator) indicator, value, unit, period
        FROM macro_indicators WHERE market = 'IN'
          AND indicator IN ('repo_rate','wpi_inflation','gdp_growth_yoy',
                            'forex_reserves_total','bank_credit_growth_yoy','usd_inr','cpi_inflation')
        ORDER BY indicator, date DESC
        """
    )
    if macro:
        parts.append("MACRO (India): " + "; ".join(
            f"{m['indicator']}={m['value']}{m['unit'] or ''} ({m['period']})" for m in macro
        ))
    if fii:
        parts.append(f"FII/DII net (₹cr, {fii['date']}): FII={fii['fii_net']}, DII={fii['dii_net']}")

    # If a stock is in focus, attach its compact profile
    sid = stock_id
    if sid is None:
        # try to resolve a symbol mentioned in the question
        token = "".join(c for c in message.upper() if c.isalnum() or c.isspace())
        words = [w for w in token.split() if len(w) >= 3]
        if words:
            hit = query_one(
                "SELECT id FROM stocks WHERE tradingsymbol = ANY(%s) LIMIT 1", (words,)
            )
            if hit:
                sid = hit["id"]

    if sid is not None:
        stock = query_one(
            "SELECT tradingsymbol AS symbol, name FROM stocks WHERE id = %s", (sid,)
        )
        if stock:
            sig = signal_for_stock(sid)
            if sig:
                parts.append(
                    f"STOCK {stock['symbol']} ({stock['name']}): verdict={sig['verdict']}, "
                    f"close={sig['close']}, RSI14={sig['rsi_14']}, MACD={sig['macd']}/{sig['macd_signal']}, "
                    f"SMA50={sig['sma_50']}, SMA200={sig['sma_200']}. "
                    f"Signals: {', '.join(s['message'] for s in sig['signals']) or 'none'}"
                )
            fund = query_one(
                "SELECT pe_ratio, pb_ratio, roe, eps, market_cap, debt_to_equity, "
                "promoter_holding_pct, roce_pct FROM fundamentals WHERE stock_id = %s "
                "ORDER BY date DESC LIMIT 1",
                (sid,),
            )
            if fund:
                parts.append("FUNDAMENTALS: " + ", ".join(
                    f"{k}={v}" for k, v in fund.items() if v is not None
                ))
            news = query_all(
                "SELECT date, headline, sentiment FROM news_sentiment WHERE stock_id = %s "
                "ORDER BY date DESC LIMIT 5",
                (sid,),
            )
            if news:
                parts.append("RECENT NEWS: " + " | ".join(
                    f"[{n['sentiment']}] {n['headline']}" for n in news
                ))
    else:
        # No specific stock — give today's signal tally so the model has market shape
        sig_rows = query_all(
            """
            SELECT s.tradingsymbol AS symbol, ti.rsi_14
            FROM watchlist w JOIN stocks s ON w.stock_id = s.id
            JOIN technical_indicators ti ON ti.stock_id = s.id
            WHERE w.name = 'Default' AND ti.date = (
                SELECT MAX(date) FROM technical_indicators ti2 WHERE ti2.stock_id = s.id)
            ORDER BY ti.rsi_14
            """
        )
        if sig_rows:
            oversold = [r["symbol"] for r in sig_rows if r["rsi_14"] and r["rsi_14"] < 35]
            overbought = [r["symbol"] for r in sig_rows if r["rsi_14"] and r["rsi_14"] > 65]
            parts.append(
                f"WATCHLIST RSI extremes — low: {', '.join(oversold) or 'none'}; "
                f"high: {', '.join(overbought) or 'none'}"
            )

    return "\n".join(parts) if parts else "No relevant rows found in the database."


def _sse(data: str, event: str | None = None) -> str:
    prefix = f"event: {event}\n" if event else ""
    return f"{prefix}data: {json.dumps({'text': data})}\n\n"


@router.post("")
def chat(req: ChatRequest):
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    def stream():
        if not api_key:
            yield _sse(
                "Claude is not configured: ANTHROPIC_API_KEY is missing from the server "
                "environment (.env). Add it and restart the backend to enable analysis chat.",
                event="error",
            )
            yield "event: done\ndata: {}\n\n"
            return

        import anthropic

        context = _build_context(req.message, req.stock_id)
        messages = list(req.history or [])
        messages.append({
            "role": "user",
            "content": f"DATA CONTEXT:\n{context}\n\nQUESTION: {req.message}",
        })

        client = anthropic.Anthropic(api_key=api_key)
        try:
            with client.messages.stream(
                model=MODEL,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=messages,
            ) as s:
                for text in s.text_stream:
                    yield _sse(text)
        except anthropic.APIStatusError as e:
            yield _sse(f"Claude API error ({e.status_code}): {e.message}", event="error")
        except Exception as e:  # noqa: BLE001 — surface any failure to the UI
            yield _sse(f"Chat failed: {e}", event="error")
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
