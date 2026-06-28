"""Stock detail — price history + indicators + news + insider/bulk + shareholding + fundamentals."""
from fastapi import APIRouter, HTTPException

from db import query_all, query_one
from signals_engine import signal_for_stock

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


@router.get("/search")
def search(q: str = "", limit: int = 20):
    """Typeahead over the stocks universe (symbol or name)."""
    if not q or len(q) < 1:
        return []
    like = f"%{q.upper()}%"
    return query_all(
        """
        SELECT id, tradingsymbol AS symbol, name, exchange
        FROM stocks
        WHERE UPPER(tradingsymbol) LIKE %s OR UPPER(name) LIKE %s
        ORDER BY (UPPER(tradingsymbol) = %s) DESC, tradingsymbol
        LIMIT %s
        """,
        (like, like, q.upper(), limit),
    )


@router.get("/{stock_id}")
def detail(stock_id: int):
    stock = query_one(
        "SELECT id, tradingsymbol AS symbol, name, exchange, segment, instrument_type "
        "FROM stocks WHERE id = %s",
        (stock_id,),
    )
    if not stock:
        raise HTTPException(404, "Stock not found")

    prices = query_all(
        "SELECT date, open, high, low, close, volume FROM daily_prices "
        "WHERE stock_id = %s ORDER BY date DESC LIMIT 250",
        (stock_id,),
    )
    indicators = query_all(
        "SELECT date, rsi_14, sma_20, sma_50, sma_200, macd, macd_signal, "
        "macd_histogram, bollinger_upper, bollinger_middle, bollinger_lower "
        "FROM technical_indicators WHERE stock_id = %s ORDER BY date DESC LIMIT 250",
        (stock_id,),
    )
    news = query_all(
        "SELECT date, headline, source, url, sentiment, sentiment_score, summary "
        "FROM news_sentiment WHERE stock_id = %s ORDER BY date DESC LIMIT 20",
        (stock_id,),
    )
    insider = query_all(
        "SELECT date, deal_type, client_name, transaction, quantity, price, source "
        "FROM bulk_deals WHERE stock_id = %s ORDER BY date DESC LIMIT 20",
        (stock_id,),
    )
    shareholding = query_all(
        "SELECT quarter_end, promoter_pct, fii_pct, dii_pct, government_pct, public_pct "
        "FROM shareholding_pattern WHERE stock_id = %s ORDER BY quarter_end DESC LIMIT 12",
        (stock_id,),
    )
    fundamentals = query_one(
        "SELECT market_cap, pe_ratio, pb_ratio, roe, debt_to_equity, eps, "
        "revenue_ttm, net_profit_ttm, opm_pct, npm_pct, roce_pct, promoter_holding_pct, "
        "pledged_pct, dividend_yield_pct, book_value, peg_ratio, ev_ebitda, screener_url "
        "FROM fundamentals WHERE stock_id = %s ORDER BY date DESC LIMIT 1",
        (stock_id,),
    )
    return {
        "stock": stock,
        "signal": signal_for_stock(stock_id),
        # return chronological (oldest first) for charts
        "prices": list(reversed(prices)),
        "indicators": list(reversed(indicators)),
        "news": news,
        "insider": insider,
        "shareholding": shareholding,
        "fundamentals": fundamentals,
    }
