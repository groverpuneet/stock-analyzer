"""Data quality — global health indicator + open-gap counts (data_quality framework)."""
from fastapi import APIRouter

from db import query_all, query_one

router = APIRouter(prefix="/api/quality", tags=["quality"])


@router.get("/health")
def health():
    """Overall data-health for the global header indicator."""
    stats = query_one(
        """
        SELECT COUNT(*) AS stocks,
               ROUND(AVG(data_completeness_score)) AS avg_completeness,
               COUNT(*) FILTER (WHERE data_completeness_score >= 90) AS green,
               COUNT(*) FILTER (WHERE data_completeness_score >= 70 AND data_completeness_score < 90) AS yellow,
               COUNT(*) FILTER (WHERE data_completeness_score < 70) AS red
        FROM stock_scores sc
        JOIN watchlist w ON w.stock_id = sc.stock_id
        JOIN stocks s ON s.id = sc.stock_id
        WHERE w.name = 'Default' AND s.exchange = 'NSE'
          AND sc.date = (SELECT MAX(date) FROM stock_scores WHERE data_completeness_score IS NOT NULL)
          AND sc.data_completeness_score IS NOT NULL
        """
    ) or {}
    open_gaps = query_one(
        "SELECT COUNT(*) AS n FROM data_quality_log WHERE resolved_at IS NULL"
    )
    return {
        "avg_completeness": float(stats["avg_completeness"]) if stats.get("avg_completeness") is not None else None,
        "stocks": stats.get("stocks", 0),
        "green": stats.get("green", 0), "yellow": stats.get("yellow", 0), "red": stats.get("red", 0),
        "open_gaps": open_gaps["n"] if open_gaps else 0,
    }


@router.get("/gaps")
def gaps():
    """Open-gap counts by table + by type — for the Data Sources page."""
    by_table = query_all(
        "SELECT table_name, COUNT(*) AS n FROM data_quality_log WHERE resolved_at IS NULL "
        "GROUP BY table_name ORDER BY n DESC"
    )
    by_type = query_all(
        "SELECT gap_type, COUNT(*) AS n FROM data_quality_log WHERE resolved_at IS NULL "
        "GROUP BY gap_type ORDER BY n DESC"
    )
    return {"by_table": by_table, "by_type": by_type}
