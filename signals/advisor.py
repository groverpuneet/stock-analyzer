"""Pillar 5 — Advisor opinions (placeholder). Weight 0 until populated.

When trusted advisor opinions are ingested into advisor_opinions, this pillar will
aggregate them. For now it returns score=None so the combiner ignores it entirely.
"""
from .util import dict_cur


def score_advisor(conn, stock_id: int) -> dict:
    opinions = []
    try:
        with dict_cur(conn) as cur:
            cur.execute(
                "SELECT advisor_name, advisor_type, opinion, target_price, published_date "
                "FROM advisor_opinions WHERE stock_id=%s ORDER BY published_date DESC LIMIT 10",
                (stock_id,))
            opinions = [dict(x) for x in cur.fetchall()]
    except Exception:
        pass
    if not opinions:
        return {"score": None, "reasoning": ["ℹ️ Advisor opinions — coming soon"],
                "key_metrics": {}, "contrary": []}
    # (future) aggregate opinions into a score
    return {"score": None, "reasoning": [f"ℹ️ {len(opinions)} advisor opinion(s) on file (scoring not yet enabled)"],
            "key_metrics": {"advisor_count": len(opinions)}, "contrary": []}
