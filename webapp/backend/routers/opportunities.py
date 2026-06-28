"""Opportunity alerts — signals worth attention that aren't already on the watchlist.

Three lenses, all from public market data:
  - sentiment_movers: stocks with strong recent positive/negative news (FinBERT scored)
  - momentum: top composite_score from the monthly model (stock_scores)
  - recent_deals: notable bulk/block deals
Each excludes whatever is already in the named watchlist.
"""
from fastapi import APIRouter

from db import query_all

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])


@router.get("")
def opportunities(watchlist: str = "Default"):
    sentiment_movers = query_all(
        """
        SELECT s.id AS stock_id, s.tradingsymbol AS symbol, s.name,
               ns.date, ns.headline, ns.source, ns.url,
               ns.sentiment, ns.sentiment_score, ns.relevance_score
        FROM news_sentiment ns
        JOIN stocks s ON ns.stock_id = s.id
        WHERE ns.sentiment_score IS NOT NULL
          AND ABS(ns.sentiment_score) >= 0.5
          AND ns.date >= CURRENT_DATE - INTERVAL '30 days'
          AND s.id NOT IN (SELECT stock_id FROM watchlist WHERE name = %s)
        ORDER BY ABS(ns.sentiment_score) DESC, ns.date DESC
        LIMIT 20
        """,
        (watchlist,),
    )
    momentum = query_all(
        """
        SELECT s.id AS stock_id, s.tradingsymbol AS symbol, s.name,
               sc.date, sc.composite_score, sc.rsi_rank, sc.momentum_score,
               sc.volume_rank, sc.macd_rank
        FROM stock_scores sc
        JOIN stocks s ON sc.stock_id = s.id
        WHERE sc.date = (SELECT MAX(date) FROM stock_scores)
          AND s.id NOT IN (SELECT stock_id FROM watchlist WHERE name = %s)
        ORDER BY sc.composite_score DESC
        LIMIT 15
        """,
        (watchlist,),
    )
    recent_deals = query_all(
        """
        SELECT s.id AS stock_id, s.tradingsymbol AS symbol, s.name,
               bd.date, bd.deal_type, bd.client_name, bd.transaction,
               bd.quantity, bd.price
        FROM bulk_deals bd
        JOIN stocks s ON bd.stock_id = s.id
        WHERE bd.date >= CURRENT_DATE - INTERVAL '30 days'
          AND s.id NOT IN (SELECT stock_id FROM watchlist WHERE name = %s)
        ORDER BY bd.date DESC, bd.quantity DESC NULLS LAST
        LIMIT 20
        """,
        (watchlist,),
    )
    return {
        "sentiment_movers": sentiment_movers,
        "momentum": momentum,
        "recent_deals": recent_deals,
    }
