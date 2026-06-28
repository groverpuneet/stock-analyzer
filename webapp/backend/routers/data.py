"""Generic raw data API for all database tables.

GET /api/data/{table} — paginated, sortable, filterable data from any table.
All endpoints are read-only. Joins stock_id to stocks.tradingsymbol where applicable.
"""
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from db import query_all, query_one

router = APIRouter(prefix="/api/data", tags=["data"])

# Table metadata: columns to show, stock_id column, date column, last_updated source
TABLE_META = {
    "analyst_targets": {
        "stock_col": "stock_id",
        "date_col": "date",
        "refresh_source": "analyst_targets",
        "order_default": "date DESC",
    },
    "bulk_deals": {
        "stock_col": "stock_id",
        "date_col": "date",
        "refresh_source": "insider_bulk",
        "order_default": "date DESC",
    },
    "concall_transcripts": {
        "stock_col": "stock_id",
        "date_col": "published_at",
        "refresh_source": "concall_transcripts",
        "order_default": "published_at DESC NULLS LAST",
    },
    "congress_trades": {
        "stock_col": "stock_id",
        "date_col": "trade_date",
        "refresh_source": "congress_trades",
        "order_default": "trade_date DESC",
    },
    "corporate_actions": {
        "stock_col": "stock_id",
        "date_col": "ex_date",
        "refresh_source": "corporate_actions",
        "order_default": "ex_date DESC NULLS LAST",
    },
    "daily_prices": {
        "stock_col": "stock_id",
        "date_col": "date",
        "refresh_source": "prices",
        "order_default": "date DESC, stock_id",
    },
    "data_quality_log": {
        "stock_col": "stock_id",
        "date_col": "detected_at",
        "refresh_source": None,
        "order_default": "detected_at DESC",
    },
    "data_refresh_log": {
        "stock_col": None,
        "date_col": "completed_at",
        "refresh_source": None,
        "order_default": "completed_at DESC NULLS LAST",
    },
    "earnings_calendar": {
        "stock_col": "stock_id",
        "date_col": "earnings_date",
        "refresh_source": "corporate_actions",
        "order_default": "earnings_date DESC",
    },
    "expiry_calendar": {
        "stock_col": None,
        "date_col": "expiry_date",
        "refresh_source": "expiry_calendar",
        "order_default": "expiry_date ASC",
    },
    "fii_dii_flows": {
        "stock_col": None,
        "date_col": "date",
        "refresh_source": "fii_dii",
        "order_default": "date DESC",
    },
    "fno_data": {
        "stock_col": None,
        "date_col": "date",
        "refresh_source": "fno_data",
        "order_default": "date DESC",
    },
    "fundamentals": {
        "stock_col": "stock_id",
        "date_col": "date",
        "refresh_source": "screener",
        "order_default": "date DESC, stock_id",
    },
    "indicator_baselines": {
        "stock_col": "stock_id",
        "date_col": "computed_at",
        "refresh_source": "model_refresh",
        "order_default": "computed_at DESC",
    },
    "insider_trades": {
        "stock_col": "stock_id",
        "date_col": "date",
        "refresh_source": "insider_bulk",
        "order_default": "date DESC",
    },
    "institutional_holdings_13f": {
        "stock_col": None,
        "date_col": "filing_date",
        "refresh_source": "sec_13f",
        "order_default": "filing_date DESC",
    },
    "macro_indicators": {
        "stock_col": None,
        "date_col": "date",
        "refresh_source": "macro",
        "order_default": "date DESC",
    },
    "mf_stock_holdings": {
        "stock_col": "stock_id",
        "date_col": "month",
        "refresh_source": "mf_stock_holdings",
        "order_default": "month DESC",
    },
    "news_sentiment": {
        "stock_col": "stock_id",
        "date_col": "date",
        "refresh_source": "news_sentiment",
        "order_default": "date DESC",
    },
    "pledging_alerts": {
        "stock_col": "stock_id",
        "date_col": "date",
        "refresh_source": "pledging_alerts",
        "order_default": "date DESC",
    },
    "quarterly_financials": {
        "stock_col": "stock_id",
        "date_col": "period_end",
        "refresh_source": "quarterly_financials",
        "order_default": "period_end DESC",
    },
    "quotes": {
        "stock_col": "stock_id",
        "date_col": "last_traded",
        "refresh_source": "prices",
        "order_default": "last_traded DESC NULLS LAST",
    },
    "recompute_queue": {
        "stock_col": "stock_id",
        "date_col": "queued_at",
        "refresh_source": None,
        "order_default": "queued_at DESC",
    },
    "sast_disclosures": {
        "stock_col": "stock_id",
        "date_col": "date",
        "refresh_source": "sast_disclosures",
        "order_default": "date DESC",
    },
    "shareholding_pattern": {
        "stock_col": "stock_id",
        "date_col": "quarter_end",
        "refresh_source": "shareholding",
        "order_default": "quarter_end DESC",
    },
    "stock_scores": {
        "stock_col": "stock_id",
        "date_col": "date",
        "refresh_source": "model_refresh",
        "order_default": "date DESC",
    },
    "stocks": {
        "stock_col": None,
        "date_col": None,
        "refresh_source": "stock_universe",
        "order_default": "tradingsymbol",
    },
    "technical_indicators": {
        "stock_col": "stock_id",
        "date_col": "date",
        "refresh_source": "indicators",
        "order_default": "date DESC, stock_id",
    },
    "tracked_filers": {
        "stock_col": None,
        "date_col": None,
        "refresh_source": "sec_13f",
        "order_default": "filer_name",
    },
    "watchlist": {
        "stock_col": "stock_id",
        "date_col": "added_at",
        "refresh_source": None,
        "order_default": "added_at DESC",
    },
    "watchlist_changes": {
        "stock_col": "stock_id",
        "date_col": "detected_at",
        "refresh_source": None,
        "order_default": "detected_at DESC",
    },
    "whatsapp_messages": {
        "stock_col": "stock_id",
        "date_col": "date",
        "refresh_source": "whatsapp",
        "order_default": "date DESC",
    },
}


def _get_columns(table: str) -> list[str]:
    """Get column names for a table."""
    rows = query_all(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table,),
    )
    return [r["column_name"] for r in rows]


def _format_value(val, col_name: str):
    """Format values for JSON output."""
    if val is None:
        return None
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="replace")
    return val


@router.get("/tables")
def list_tables():
    """List all available tables with metadata."""
    tables = []
    for name, meta in TABLE_META.items():
        cols = _get_columns(name)
        row = query_one(f"SELECT COUNT(*) AS cnt FROM {name}")
        tables.append({
            "name": name,
            "columns": cols,
            "row_count": row["cnt"] if row else 0,
            "has_stock": meta["stock_col"] is not None,
            "date_column": meta["date_col"],
            "refresh_source": meta["refresh_source"],
        })
    return {"tables": tables}


@router.get("/{table}")
def get_table_data(
    table: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    sort_by: Optional[str] = None,
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    filter_stock: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    search: Optional[str] = None,
):
    """Get paginated data from any table."""
    if table not in TABLE_META:
        raise HTTPException(404, f"Table '{table}' not found")

    meta = TABLE_META[table]
    columns = _get_columns(table)

    if not columns:
        raise HTTPException(404, f"Table '{table}' has no columns")

    # Build SELECT with stock symbol join if applicable
    stock_col = meta["stock_col"]
    if stock_col and stock_col in columns:
        select = f"t.*, s.tradingsymbol AS symbol"
        from_clause = f"{table} t LEFT JOIN stocks s ON t.{stock_col} = s.id"
    else:
        select = "t.*"
        from_clause = f"{table} t"

    # Build WHERE conditions
    conditions = []
    params = []

    if filter_stock and stock_col:
        conditions.append(f"t.{stock_col} = %s")
        params.append(filter_stock)

    date_col = meta["date_col"]
    if date_from and date_col:
        conditions.append(f"t.{date_col} >= %s")
        params.append(date_from)
    if date_to and date_col:
        conditions.append(f"t.{date_col} <= %s")
        params.append(date_to)

    # Text search across string columns
    if search:
        text_cols = []
        col_info = query_all(
            """
            SELECT column_name, data_type FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            AND data_type IN ('character varying', 'text', 'character')
            """,
            (table,),
        )
        text_cols = [c["column_name"] for c in col_info]
        if text_cols:
            or_clauses = " OR ".join(f"LOWER(t.{c}::text) LIKE %s" for c in text_cols)
            conditions.append(f"({or_clauses})")
            params.extend([f"%{search.lower()}%"] * len(text_cols))

    where_clause = " AND ".join(conditions) if conditions else "TRUE"

    # Validate sort column
    if sort_by:
        if sort_by not in columns and sort_by != "symbol":
            sort_by = None
    if sort_by:
        order = f"t.{sort_by} {sort_dir.upper()} NULLS LAST"
    else:
        order = meta["order_default"]

    # Get total count
    count_sql = f"SELECT COUNT(*) AS cnt FROM {from_clause} WHERE {where_clause}"
    total = query_one(count_sql, tuple(params))["cnt"]

    # Get paginated data
    offset = (page - 1) * per_page
    data_sql = f"""
        SELECT {select} FROM {from_clause}
        WHERE {where_clause}
        ORDER BY {order}
        LIMIT %s OFFSET %s
    """
    rows = query_all(data_sql, tuple(params) + (per_page, offset))

    # Format values
    formatted = []
    for row in rows:
        formatted.append({k: _format_value(v, k) for k, v in row.items()})

    # Get last updated timestamp
    last_updated = None
    if meta["refresh_source"]:
        lu_row = query_one(
            "SELECT completed_at FROM data_refresh_log WHERE source = %s ORDER BY completed_at DESC NULLS LAST LIMIT 1",
            (meta["refresh_source"],),
        )
        if lu_row and lu_row["completed_at"]:
            last_updated = lu_row["completed_at"].isoformat()

    return {
        "table": table,
        "columns": columns + (["symbol"] if stock_col else []),
        "data": formatted,
        "total_count": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page,
        "last_updated": last_updated,
    }


@router.get("/{table}/export")
def export_csv(
    table: str,
    filter_stock: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    search: Optional[str] = None,
):
    """Export table data as CSV (all rows matching filters, no pagination)."""
    from fastapi.responses import StreamingResponse
    import csv
    import io

    if table not in TABLE_META:
        raise HTTPException(404, f"Table '{table}' not found")

    meta = TABLE_META[table]
    columns = _get_columns(table)

    stock_col = meta["stock_col"]
    if stock_col and stock_col in columns:
        select = f"t.*, s.tradingsymbol AS symbol"
        from_clause = f"{table} t LEFT JOIN stocks s ON t.{stock_col} = s.id"
        columns = columns + ["symbol"]
    else:
        select = "t.*"
        from_clause = f"{table} t"

    conditions = []
    params = []

    if filter_stock and stock_col:
        conditions.append(f"t.{stock_col} = %s")
        params.append(filter_stock)

    date_col = meta["date_col"]
    if date_from and date_col:
        conditions.append(f"t.{date_col} >= %s")
        params.append(date_from)
    if date_to and date_col:
        conditions.append(f"t.{date_col} <= %s")
        params.append(date_to)

    if search:
        col_info = query_all(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            AND data_type IN ('character varying', 'text', 'character')
            """,
            (table,),
        )
        text_cols = [c["column_name"] for c in col_info]
        if text_cols:
            or_clauses = " OR ".join(f"LOWER(t.{c}::text) LIKE %s" for c in text_cols)
            conditions.append(f"({or_clauses})")
            params.extend([f"%{search.lower()}%"] * len(text_cols))

    where_clause = " AND ".join(conditions) if conditions else "TRUE"
    order = meta["order_default"]

    sql = f"SELECT {select} FROM {from_clause} WHERE {where_clause} ORDER BY {order}"
    rows = query_all(sql, tuple(params))

    # Stream CSV
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        formatted = {k: _format_value(v, k) for k, v in row.items()}
        writer.writerow(formatted)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={table}.csv"},
    )
