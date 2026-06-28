"""Smart Money API — 13F holdings, SAST, insider trades, DII trends."""
from fastapi import APIRouter

from db import query_all

router = APIRouter(prefix="/api/smart-money", tags=["smart-money"])


@router.get("/13f")
def get_13f_holdings(limit: int = 100):
    """13F holdings with filer names, sorted by value."""
    rows = query_all("""
        SELECT
            h.id,
            tf.filer_name,
            tf.category AS filer_category,
            h.symbol,
            h.issuer_name,
            h.shares_held,
            h.market_value_usd,
            h.pct_of_portfolio,
            h.qoq_change_shares,
            h.qoq_change_pct,
            h.quarter,
            h.filing_date
        FROM institutional_holdings_13f h
        JOIN tracked_filers tf ON h.filer_cik = tf.filer_cik
        ORDER BY h.filing_date DESC, h.market_value_usd DESC
        LIMIT %s
    """, (limit,))
    return {"holdings": rows, "total": len(rows)}


@router.get("/sast")
def get_sast_disclosures(limit: int = 100):
    """SAST disclosures — large acquisitions in India."""
    rows = query_all("""
        SELECT
            sd.id,
            sd.stock_id,
            s.tradingsymbol AS symbol,
            sd.acquirer_name,
            sd.acquirer_type,
            sd.shares_acquired,
            sd.pct_acquired,
            sd.total_holding_pct,
            sd.acquisition_date,
            sd.disclosure_date,
            sd.transaction_type
        FROM sast_disclosures sd
        LEFT JOIN stocks s ON sd.stock_id = s.id
        ORDER BY sd.disclosure_date DESC NULLS LAST, sd.acquisition_date DESC
        LIMIT %s
    """, (limit,))
    return {"disclosures": rows, "total": len(rows)}


@router.get("/insider")
def get_insider_trades(limit: int = 100, market: str = "all"):
    """Insider trades — buy/sell activity by insiders."""
    market_filter = ""
    params = [limit]
    if market == "india":
        market_filter = "AND it.source != 'sec_form4'"
    elif market == "us":
        market_filter = "AND it.source = 'sec_form4'"

    rows = query_all(f"""
        SELECT
            it.id,
            it.stock_id,
            s.tradingsymbol AS symbol,
            s.exchange,
            it.date,
            it.person_name,
            it.person_category,
            it.transaction,
            it.quantity,
            it.price,
            it.post_trade_pct,
            it.source
        FROM insider_trades it
        LEFT JOIN stocks s ON it.stock_id = s.id
        WHERE 1=1 {market_filter}
        ORDER BY it.date DESC
        LIMIT %s
    """, tuple(params))
    return {"trades": rows, "total": len(rows)}


@router.get("/dii-trend")
def get_dii_trend(limit: int = 50):
    """DII ownership trends from shareholding_pattern."""
    rows = query_all("""
        WITH ranked AS (
            SELECT
                sp.stock_id,
                s.tradingsymbol AS symbol,
                sp.quarter_end,
                sp.dii_pct,
                LAG(sp.dii_pct) OVER (PARTITION BY sp.stock_id ORDER BY sp.quarter_end) AS prev_dii_pct,
                ROW_NUMBER() OVER (PARTITION BY sp.stock_id ORDER BY sp.quarter_end DESC) AS rn
            FROM shareholding_pattern sp
            JOIN stocks s ON sp.stock_id = s.id
            WHERE sp.dii_pct IS NOT NULL
        )
        SELECT
            stock_id,
            symbol,
            quarter_end,
            dii_pct,
            prev_dii_pct,
            ROUND((dii_pct - COALESCE(prev_dii_pct, dii_pct))::numeric, 2) AS change_pct
        FROM ranked
        WHERE rn = 1 AND prev_dii_pct IS NOT NULL
        ORDER BY (dii_pct - prev_dii_pct) DESC
        LIMIT %s
    """, (limit,))
    return {"trends": rows, "total": len(rows)}


@router.get("/insider-clusters")
def get_insider_clusters(days: int = 30):
    """Stocks with multiple insider buys in last N days."""
    rows = query_all("""
        SELECT
            it.stock_id,
            s.tradingsymbol AS symbol,
            s.exchange,
            COUNT(*) AS trade_count,
            SUM(CASE WHEN it.transaction = 'BUY' THEN 1 ELSE 0 END) AS buy_count,
            SUM(CASE WHEN it.transaction = 'SELL' THEN 1 ELSE 0 END) AS sell_count,
            SUM(it.quantity * COALESCE(it.price, 0)) AS total_value,
            MAX(it.date) AS latest_date
        FROM insider_trades it
        JOIN stocks s ON it.stock_id = s.id
        WHERE it.date >= CURRENT_DATE - %s
        GROUP BY it.stock_id, s.tradingsymbol, s.exchange
        HAVING COUNT(*) >= 2
        ORDER BY buy_count DESC, trade_count DESC
        LIMIT 50
    """, (days,))
    return {"clusters": rows, "total": len(rows)}
