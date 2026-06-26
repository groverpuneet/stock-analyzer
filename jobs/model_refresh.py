"""
jobs/model_refresh.py — Monthly model refresh

Three steps (run in order):
  1. refresh_signal_scores() — composite 0-100 quant score per stock from
     52-week percentile ranks of RSI, momentum, volume, MACD histogram.
     Stored in stock_scores table.

  2. refresh_finbert() — invalidate local HuggingFace cache for
     ProsusAI/finbert and re-download to pick up any weight updates.

  3. refresh_indicator_baselines() — 52W rolling stats (mean, std,
     p10/p25/p75/p90) per stock for rsi_14, volume, macd_histogram, macd.
     Stored in indicator_baselines table.

Schedule: first Sunday of each month, 06:00 IST
Usage:
  python jobs/model_refresh.py              # all three steps
  python jobs/model_refresh.py --scores     # composite scores only
  python jobs/model_refresh.py --finbert    # FinBERT cache only
  python jobs/model_refresh.py --baselines  # indicator baselines only
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.db import get_conn, refresh_log
from utils.logger import get_logger

log = get_logger(__name__)


def _get_all_stocks():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, tradingsymbol FROM stocks ORDER BY tradingsymbol")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows


def _percentile_rank(value, history):
    """Fraction of history values <= value, scaled 0-100."""
    if not history:
        return 50.0
    return round(sum(1 for h in history if h <= value) / len(history) * 100, 1)


# ── Step 1: Composite signal scores ───────────────────────────────────────────

def refresh_signal_scores():
    """
    Composite 0-100 score for each stock using 52W percentile ranks:
      rsi_rank    = where today's RSI sits in its own 52W RSI distribution
      momentum    = (close - 52W low) / (52W high - 52W low) * 100
      volume_rank = where 5d avg volume sits in own 52W volume distribution
      macd_rank   = where today's MACD histogram sits in own 52W distribution
      composite   = 0.30*rsi + 0.30*momentum + 0.20*volume + 0.20*macd
    """
    import numpy as np

    log.info("Step 1: Computing composite signal scores...")
    stocks = _get_all_stocks()
    conn = get_conn(); cur = conn.cursor(); scored = 0; today = date.today()

    for stock_id, symbol in stocks:
        try:
            cur.execute("""
                SELECT dp.close, dp.volume, ti.rsi_14, ti.macd_histogram
                FROM daily_prices dp
                LEFT JOIN technical_indicators ti
                    ON dp.stock_id = ti.stock_id AND dp.date = ti.date
                WHERE dp.stock_id = %s
                  AND dp.date >= CURRENT_DATE - INTERVAL '365 days'
                ORDER BY dp.date
            """, (stock_id,))
            rows = cur.fetchall()

            if len(rows) < 20:
                continue

            closes  = [float(r[0]) for r in rows if r[0] is not None]
            volumes = [float(r[1]) for r in rows if r[1] is not None]
            rsis    = [float(r[2]) for r in rows if r[2] is not None]
            macds   = [float(r[3]) for r in rows if r[3] is not None]

            if not closes or not rsis:
                continue

            high_52w = max(closes)
            low_52w  = min(closes)
            momentum = ((closes[-1] - low_52w) / (high_52w - low_52w) * 100
                        if high_52w != low_52w else 50.0)

            avg_vol_5d  = float(np.mean(volumes[-5:])) if len(volumes) >= 5 else float(np.mean(volumes))
            rsi_rank    = _percentile_rank(rsis[-1], rsis)
            volume_rank = _percentile_rank(avg_vol_5d, volumes)
            macd_rank   = _percentile_rank(macds[-1], macds) if macds else 50.0

            composite = round(
                0.30 * rsi_rank +
                0.30 * momentum +
                0.20 * volume_rank +
                0.20 * macd_rank,
                1
            )

            cur.execute("""
                INSERT INTO stock_scores
                    (stock_id, date, rsi_rank, momentum_score,
                     volume_rank, macd_rank, composite_score)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (stock_id, date) DO UPDATE SET
                    rsi_rank       = EXCLUDED.rsi_rank,
                    momentum_score = EXCLUDED.momentum_score,
                    volume_rank    = EXCLUDED.volume_rank,
                    macd_rank      = EXCLUDED.macd_rank,
                    composite_score = EXCLUDED.composite_score
            """, (stock_id, today, rsi_rank, round(momentum, 1),
                  volume_rank, macd_rank, composite))
            scored += 1

        except Exception as e:
            log.warning(f"  Score failed for {symbol}: {e}")

    conn.commit(); cur.close(); conn.close()
    log.info(f"  Scored {scored}/{len(stocks)} stocks")
    return scored


# ── Step 2: FinBERT cache refresh ─────────────────────────────────────────────

def refresh_finbert():
    """
    Delete the local HuggingFace cache for ProsusAI/finbert and re-download.
    Safe to run even if no cache exists.
    """
    import shutil

    log.info("Step 2: Refreshing FinBERT weights...")
    model_dir = os.path.expanduser(
        '~/.cache/huggingface/hub/models--ProsusAI--finbert'
    )

    if os.path.exists(model_dir):
        size_mb = sum(
            os.path.getsize(os.path.join(d, f))
            for d, _, files in os.walk(model_dir)
            for f in files
        ) / 1_048_576
        log.info(f"  Removing cached model ({size_mb:.0f} MB)...")
        shutil.rmtree(model_dir)
    else:
        log.info("  No existing cache — fresh download")

    log.info("  Downloading ProsusAI/finbert...")
    from transformers import BertTokenizer, BertForSequenceClassification
    BertTokenizer.from_pretrained('ProsusAI/finbert')
    BertForSequenceClassification.from_pretrained('ProsusAI/finbert')
    log.info("  FinBERT weights updated")
    return 1


# ── Step 3: Indicator baselines ───────────────────────────────────────────────

def refresh_indicator_baselines():
    """
    52W rolling stats (mean, std, p10/p25/p75/p90) per stock per indicator.
    These context stats let the signal generator judge whether today's value
    is exceptional vs typical for that specific stock.
    """
    import numpy as np

    log.info("Step 3: Computing indicator baselines...")
    stocks = _get_all_stocks()
    conn = get_conn(); cur = conn.cursor(); processed = 0; today = date.today()

    for stock_id, symbol in stocks:
        try:
            cur.execute("""
                SELECT dp.volume, ti.rsi_14, ti.macd_histogram, ti.macd
                FROM daily_prices dp
                LEFT JOIN technical_indicators ti
                    ON dp.stock_id = ti.stock_id AND dp.date = ti.date
                WHERE dp.stock_id = %s
                  AND dp.date >= CURRENT_DATE - INTERVAL '365 days'
                ORDER BY dp.date
            """, (stock_id,))
            rows = cur.fetchall()

            if len(rows) < 20:
                continue

            series = {
                'volume':         [float(r[0]) for r in rows if r[0] is not None],
                'rsi_14':         [float(r[1]) for r in rows if r[1] is not None],
                'macd_histogram': [float(r[2]) for r in rows if r[2] is not None],
                'macd':           [float(r[3]) for r in rows if r[3] is not None],
            }

            for indicator, values in series.items():
                if len(values) < 10:
                    continue
                arr = np.array(values, dtype=float)
                cur.execute("""
                    INSERT INTO indicator_baselines
                        (stock_id, computed_date, indicator, mean_val, std_val,
                         p10, p25, p75, p90)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (stock_id, computed_date, indicator) DO UPDATE SET
                        mean_val = EXCLUDED.mean_val,
                        std_val  = EXCLUDED.std_val,
                        p10      = EXCLUDED.p10,
                        p25      = EXCLUDED.p25,
                        p75      = EXCLUDED.p75,
                        p90      = EXCLUDED.p90
                """, (
                    stock_id, today, indicator,
                    round(float(np.mean(arr)), 4),
                    round(float(np.std(arr)),  4),
                    round(float(np.percentile(arr, 10)), 4),
                    round(float(np.percentile(arr, 25)), 4),
                    round(float(np.percentile(arr, 75)), 4),
                    round(float(np.percentile(arr, 90)), 4),
                ))

            processed += 1

        except Exception as e:
            log.warning(f"  Baseline failed for {symbol}: {e}")

    conn.commit(); cur.close(); conn.close()
    log.info(f"  Baselines computed for {processed}/{len(stocks)} stocks")
    return processed


# ── Main ──────────────────────────────────────────────────────────────────────

def run_model_refresh():
    log.info("=== Monthly model refresh starting ===")
    with refresh_log('model_refresh') as rlog:
        n_scores    = refresh_signal_scores()
        n_finbert   = refresh_finbert()
        n_baselines = refresh_indicator_baselines()
        rlog['rows'] = n_scores + n_finbert + n_baselines
    log.info(f"=== Model refresh complete — {n_scores} scores, {n_baselines} baselines ===")
    _print_top_scores()


def _print_top_scores():
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""
        SELECT s.tradingsymbol, sc.composite_score,
               sc.rsi_rank, sc.momentum_score, sc.volume_rank
        FROM stock_scores sc
        JOIN stocks s ON sc.stock_id = s.id
        WHERE sc.date = CURRENT_DATE
        ORDER BY sc.composite_score DESC
        LIMIT 20
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()

    if not rows:
        print("No scores computed for today yet")
        return

    print(f"\n{'='*65}")
    print(f"COMPOSITE STOCK SCORES — {date.today()}")
    print(f"{'='*65}")
    print(f"  {'Symbol':<14} {'Score':>6} {'RSI%':>6} {'Mom%':>6} {'Vol%':>6}")
    print(f"  {'-'*50}")
    for sym, comp, rsi, mom, vol in rows:
        print(f"  {sym:<14} {comp:>6.1f} {rsi:>6.1f} {mom:>6.1f} {vol:>6.1f}")
    print(f"{'='*65}\n")


if __name__ == '__main__':
    args = sys.argv[1:]
    if '--scores' in args:
        refresh_signal_scores()
        _print_top_scores()
    elif '--finbert' in args:
        refresh_finbert()
    elif '--baselines' in args:
        refresh_indicator_baselines()
    else:
        run_model_refresh()
