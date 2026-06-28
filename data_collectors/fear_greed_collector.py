"""
data_collectors/fear_greed_collector.py  (Part 9)

US Fear & Greed  — fetched from CNN's free dataviz API.
India Fear & Greed — computed 0-100 from market internals:
  VIX (low=greed), Put/Call ratio (low=greed), FII net flow (buy=greed),
  % watchlist above SMA50, % watchlist RSI>50, avg news sentiment.

Both stored in macro_indicators:
  indicator='us_fear_greed_index' (market='US') / 'india_fear_greed_index' (market='IN')
"""
import os
import sys
import logging
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from utils.db import get_conn, refresh_log

log = logging.getLogger(__name__)
H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
CNN_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"


def _clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


def _store(market, indicator, value, period, source, for_date=None):
    """Store indicator. Uses ON CONFLICT DO NOTHING to preserve historical data."""
    conn = get_conn(); cur = conn.cursor()
    d = for_date or date.today()
    cur.execute("""
        INSERT INTO macro_indicators (date, market, indicator, value, unit, period, source)
        VALUES (%s,%s,%s,%s,'index',%s,%s)
        ON CONFLICT (date, market, indicator) DO NOTHING
    """, (d, market, indicator, round(value, 1), period, source))
    conn.commit(); cur.close(); conn.close()


def collect_us_fear_greed() -> dict:
    r = requests.get(CNN_URL, headers=H, timeout=15)
    r.raise_for_status()
    fg = r.json().get("fear_and_greed", {})
    score = fg.get("score")
    if score is None:
        raise RuntimeError("CNN F&G returned no score")
    _store("US", "us_fear_greed_index", float(score), fg.get("rating", ""), "cnn")
    # also backfill recent history so the 30-day chart has data
    conn = get_conn(); cur = conn.cursor()
    hist = r.json().get("fear_and_greed_historical", {}).get("data", [])
    n = 0
    for pt in hist[-40:]:
        d = datetime.utcfromtimestamp(pt["x"] / 1000).date()
        cur.execute("""
            INSERT INTO macro_indicators (date, market, indicator, value, unit, period, source)
            VALUES (%s,'US','us_fear_greed_index',%s,'index',%s,'cnn')
            ON CONFLICT (date, market, indicator) DO UPDATE SET value=EXCLUDED.value
        """, (d, round(float(pt["y"]), 1), d.strftime("%d-%b")))
        n += 1
    conn.commit(); cur.close(); conn.close()
    log.info(f"US F&G: {score:.0f} ({fg.get('rating')}), {n} history points")
    return {"score": round(float(score), 1), "rating": fg.get("rating"), "history": n}


def compute_india_fear_greed_for_date(target_date: date) -> dict | None:
    """Compute India F&G for a specific past date using historical data."""
    conn = get_conn(); cur = conn.cursor()
    comps = {}

    # 1. India VIX (low = greed): 10 -> 100, 30 -> 0
    cur.execute("SELECT india_vix FROM fno_data WHERE date <= %s ORDER BY date DESC LIMIT 1", (target_date,))
    row = cur.fetchone()
    if row and row[0] is not None:
        comps["vix"] = _clamp(100 - (float(row[0]) - 10) / 20 * 100)

    # 2. Put/Call ratio (low = greed): 0.7 -> 100, 1.3 -> 0
    cur.execute("SELECT total_pcr, index_pcr FROM fno_data WHERE date <= %s ORDER BY date DESC LIMIT 1", (target_date,))
    row = cur.fetchone()
    pcr = (row[0] or row[1]) if row else None
    if pcr is not None:
        comps["pcr"] = _clamp((1.3 - float(pcr)) / 0.6 * 100)

    # 3. FII net flow (buy = greed): +5000cr -> 100, -5000cr -> 0
    cur.execute("SELECT fii_net FROM fii_dii_flows WHERE date <= %s AND fii_net IS NOT NULL ORDER BY date DESC LIMIT 1", (target_date,))
    row = cur.fetchone()
    if row and row[0] is not None:
        comps["fii"] = _clamp(50 + float(row[0]) / 5000 * 50)

    # 4. % watchlist above SMA50  &  5. % RSI>50 (on target_date)
    cur.execute("""
        SELECT
          AVG(CASE WHEN dp.close > ti.sma_50 THEN 100.0 ELSE 0 END),
          AVG(CASE WHEN ti.rsi_14 > 50 THEN 100.0 ELSE 0 END)
        FROM watchlist w JOIN stocks s ON w.stock_id=s.id
        JOIN technical_indicators ti ON ti.stock_id=s.id AND ti.date = %s
        JOIN daily_prices dp ON dp.stock_id=s.id AND dp.date = %s
        WHERE w.name='Default' AND s.exchange='NSE' AND ti.sma_50 IS NOT NULL AND ti.rsi_14 IS NOT NULL
    """, (target_date, target_date))
    row = cur.fetchone()
    if row and row[0] is not None:
        comps["above_sma50"] = float(row[0])
    if row and row[1] is not None:
        comps["rsi_gt_50"] = float(row[1])

    # 6. Avg news sentiment for week ending on target_date
    cur.execute("""
        SELECT AVG(n.sentiment_score) FROM news_sentiment n
        JOIN watchlist w ON w.stock_id=n.stock_id JOIN stocks s ON s.id=n.stock_id
        WHERE w.name='Default' AND n.date BETWEEN %s - 7 AND %s AND n.sentiment_score IS NOT NULL
    """, (target_date, target_date))
    row = cur.fetchone()
    if row and row[0] is not None:
        comps["sentiment"] = _clamp((float(row[0]) + 1) / 2 * 100)

    cur.close(); conn.close()
    if not comps:
        return None
    score = sum(comps.values()) / len(comps)
    rating = ("Extreme Fear" if score < 25 else "Fear" if score < 45 else
              "Neutral" if score < 55 else "Greed" if score < 75 else "Extreme Greed")
    return {"score": round(score, 1), "rating": rating, "components": comps}


def backfill_india_fear_greed(days: int = 30) -> int:
    """Backfill India F&G history for the last N days."""
    from datetime import timedelta
    conn = get_conn(); cur = conn.cursor()
    # Get distinct dates with technical indicator data
    cur.execute("""
        SELECT DISTINCT ti.date FROM technical_indicators ti
        WHERE ti.date >= CURRENT_DATE - %s ORDER BY ti.date
    """, (days,))
    dates = [r[0] for r in cur.fetchall()]
    cur.close(); conn.close()

    count = 0
    for d in dates:
        result = compute_india_fear_greed_for_date(d)
        if result:
            _store("IN", "india_fear_greed_index", result["score"], result["rating"], "computed", for_date=d)
            count += 1
            log.info(f"India F&G backfill {d}: {result['score']:.0f} ({result['rating']})")
    return count


def compute_india_fear_greed() -> dict:
    conn = get_conn(); cur = conn.cursor()
    comps = {}

    # 1. India VIX (low = greed): 10 -> 100, 30 -> 0
    cur.execute("SELECT india_vix FROM fno_data ORDER BY date DESC LIMIT 1")
    row = cur.fetchone()
    if row and row[0] is not None:
        comps["vix"] = _clamp(100 - (float(row[0]) - 10) / 20 * 100)

    # 2. Put/Call ratio (low = greed): 0.7 -> 100, 1.3 -> 0
    cur.execute("SELECT total_pcr, index_pcr FROM fno_data ORDER BY date DESC LIMIT 1")
    row = cur.fetchone()
    pcr = (row[0] or row[1]) if row else None
    if pcr is not None:
        comps["pcr"] = _clamp((1.3 - float(pcr)) / 0.6 * 100)

    # 3. FII net flow (buy = greed): +5000cr -> 100, -5000cr -> 0
    cur.execute("SELECT fii_net FROM fii_dii_flows WHERE fii_net IS NOT NULL ORDER BY date DESC LIMIT 1")
    row = cur.fetchone()
    if row and row[0] is not None:
        comps["fii"] = _clamp(50 + float(row[0]) / 5000 * 50)

    # 4. % watchlist above SMA50  &  5. % RSI>50
    cur.execute("""
        SELECT
          AVG(CASE WHEN dp.close > ti.sma_50 THEN 100.0 ELSE 0 END),
          AVG(CASE WHEN ti.rsi_14 > 50 THEN 100.0 ELSE 0 END)
        FROM watchlist w JOIN stocks s ON w.stock_id=s.id
        JOIN technical_indicators ti ON ti.stock_id=s.id
          AND ti.date=(SELECT MAX(date) FROM technical_indicators t2 WHERE t2.stock_id=s.id)
        JOIN daily_prices dp ON dp.stock_id=s.id AND dp.date=ti.date
        WHERE w.name='Default' AND s.exchange='NSE' AND ti.sma_50 IS NOT NULL AND ti.rsi_14 IS NOT NULL
    """)
    row = cur.fetchone()
    if row and row[0] is not None:
        comps["above_sma50"] = float(row[0])
    if row and row[1] is not None:
        comps["rsi_gt_50"] = float(row[1])

    # 6. Avg news sentiment (-1..1 -> 0..100)
    cur.execute("""
        SELECT AVG(n.sentiment_score) FROM news_sentiment n
        JOIN watchlist w ON w.stock_id=n.stock_id JOIN stocks s ON s.id=n.stock_id
        WHERE w.name='Default' AND n.date >= CURRENT_DATE - 7 AND n.sentiment_score IS NOT NULL
    """)
    row = cur.fetchone()
    if row and row[0] is not None:
        comps["sentiment"] = _clamp((float(row[0]) + 1) / 2 * 100)

    cur.close(); conn.close()
    if not comps:
        raise RuntimeError("No components available for India F&G")
    score = sum(comps.values()) / len(comps)
    rating = ("Extreme Fear" if score < 25 else "Fear" if score < 45 else
              "Neutral" if score < 55 else "Greed" if score < 75 else "Extreme Greed")
    _store("IN", "india_fear_greed_index", score, rating, "computed")
    log.info(f"India F&G: {score:.0f} ({rating}) from {comps}")
    return {"score": round(score, 1), "rating": rating, "components": {k: round(v, 1) for k, v in comps.items()}}


def collect_fear_greed() -> dict:
    out = {}
    with refresh_log("fear_greed") as meta:
        n = 0
        try:
            out["us"] = collect_us_fear_greed(); n += 1
        except Exception as e:  # noqa: BLE001
            log.error(f"US F&G failed: {e}")
        try:
            out["india"] = compute_india_fear_greed(); n += 1
        except Exception as e:  # noqa: BLE001
            log.error(f"India F&G failed: {e}")
        meta["rows"] = n
    return out


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--backfill", type=int, help="Backfill India F&G for N days")
    args = parser.parse_args()
    if args.backfill:
        n = backfill_india_fear_greed(args.backfill)
        print(f"Backfilled {n} days of India Fear & Greed")
    else:
        print(collect_fear_greed())
