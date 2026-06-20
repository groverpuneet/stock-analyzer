"""
data_collectors/news_sentiment_collector.py
Daily refresh — 5:15 PM IST (after signal report runs at 5:00 PM)

Pipeline:
  1. Fetch RSS headlines from Economic Times + Moneycontrol + Google News
  2. Filter headlines mentioning each watchlist stock
  3. Score with FinBERT locally (free, no API key needed)
  4. Store in news_sentiment table
  5. Sentiment feeds into tomorrow's pre-market signal report

Engineering concepts:
  - FinBERT: BERT model fine-tuned on financial news from ProsusAI
    Understands financial language — "correction", "bears", "volatile"
    mean different things in finance vs everyday English
  - Model singleton: load model once at module level, reuse across all stocks
    Loading a 438MB model takes ~3 seconds — doing it per stock would be
    prohibitively slow for 150 stocks
  - RSS parsing: feedparser library handles all RSS/Atom format variants
  - Batch scoring: score all headlines for one stock in one forward pass

Usage:
    python data_collectors/news_sentiment_collector.py
    python data_collectors/news_sentiment_collector.py --stock RELIANCE
"""
import os
import sys
import time
import hashlib
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import get_conn, refresh_log, get_watchlist_stocks
from utils.logger import get_logger

log = get_logger(__name__)

# ── RSS feed templates ─────────────────────────────────────────────────────────
# {symbol} and {company} are replaced per stock
# Engineering note: Google News RSS is particularly good — it aggregates
# from ET, Moneycontrol, Business Standard, Mint, all in one feed
RSS_TEMPLATES = [
    "https://news.google.com/rss/search?q={company}+stock+NSE&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/search?q={symbol}+share+price&hl=en-IN&gl=IN&ceid=IN:en",
    "https://economictimes.indiatimes.com/markets/stocks/news/rssfeeds/{et_slug}.cms",
]

# Company name overrides for better search results
# Engineering note: "BHARTIARTL" won't get good results, "Bharti Airtel" will
COMPANY_NAMES = {
    "BHARTIARTL": "Bharti Airtel",
    "HDFCBANK":   "HDFC Bank",
    "ICICIBANK":  "ICICI Bank",
    "INFY":       "Infosys",
    "ITC":        "ITC Limited",
    "KOTAKBANK":  "Kotak Mahindra Bank",
    "RELIANCE":   "Reliance Industries",
    "SBIN":       "State Bank of India SBI",
    "TCS":        "Tata Consultancy Services TCS",
    "WIPRO":      "Wipro",
}


# ── FinBERT model (loaded once at module level) ────────────────────────────────
# Engineering note on the singleton pattern:
#   Loading the 438MB FinBERT model takes ~3 seconds and ~1GB RAM.
#   We load it once when this module is first imported, then reuse the same
#   model object for every stock. If we loaded inside the function, we'd
#   pay the 3-second cost 150 times for 150 stocks = 7.5 minutes just loading.
#   Module-level loading = load once, use forever.

_model = None
_tokenizer = None


def _load_finbert():
    """Load FinBERT model lazily — when first needed."""
    global _model, _tokenizer
    if _model is not None:
        return _model, _tokenizer

    log.info("Loading FinBERT model (first use only)...")
    try:
        from transformers import BertTokenizer, BertForSequenceClassification
        import torch

        _tokenizer = BertTokenizer.from_pretrained('ProsusAI/finbert')
        _model = BertForSequenceClassification.from_pretrained('ProsusAI/finbert')
        _model.eval()   # inference mode — disables dropout, faster + deterministic
        log.info("FinBERT loaded successfully")
        return _model, _tokenizer
    except Exception as e:
        log.error(f"Failed to load FinBERT: {e}")
        raise


def score_headlines(headlines: list) -> list:
    """
    Score a list of headlines with FinBERT.

    Engineering note on batching:
      We tokenize all headlines together and run one forward pass through
      the model. This is much faster than one pass per headline because
      the GPU/CPU can process them in parallel. For 5 headlines, batching
      is ~3x faster than sequential scoring.

    Returns list of dicts:
      { 'headline': str, 'sentiment': str, 'score': float, 'confidence': float }
      score: +1.0 = very positive, -1.0 = very negative, 0.0 = neutral
    """
    if not headlines:
        return []

    import torch

    model, tokenizer = _load_finbert()

    # Tokenize all headlines in one batch
    # truncation=True: cut headlines longer than 512 tokens (model limit)
    # padding=True: pad shorter headlines to same length for batch processing
    inputs = tokenizer(
        headlines,
        return_tensors='pt',
        truncation=True,
        max_length=512,
        padding=True
    )

    with torch.no_grad():   # no_grad: don't compute gradients (inference only, faster)
        outputs = model(**inputs)

    # Softmax converts raw logits to probabilities that sum to 1.0
    # FinBERT output order: [positive, negative, neutral]
    probs = torch.softmax(outputs.logits, dim=1).tolist()
    labels = ['positive', 'negative', 'neutral']

    results = []
    for headline, prob in zip(headlines, probs):
        pos, neg, neu = prob
        sentiment = labels[prob.index(max(prob))]

        # Convert to -1 to +1 scale
        # Engineering note: we use (pos - neg) rather than just max prob
        # because a headline that's 40% positive, 35% negative, 25% neutral
        # should score close to 0, not +0.4 (which max prob would give)
        score = round(pos - neg, 3)
        confidence = round(max(prob), 3)

        results.append({
            'headline':   headline,
            'sentiment':  sentiment,
            'score':      score,
            'confidence': confidence,
        })
        log.debug(f"  {sentiment:8} {score:+.2f} (conf={confidence:.2f}) | {headline[:60]}")

    return results


# ── RSS fetching ────────────────────────────────────────────────────────────────

def fetch_rss_headlines(symbol: str, max_per_feed: int = 10) -> list:
    """
    Fetch recent headlines for a stock from Google News RSS.

    Engineering note on feedparser:
      feedparser handles all RSS/Atom variants and date formats automatically.
      It also sanitizes HTML in descriptions, handles encoding, and follows
      redirects. Much more robust than writing our own XML parser.

    Returns list of { 'title': str, 'url': str, 'published': datetime }
    """
    try:
        import feedparser
    except ImportError:
        log.error("feedparser not installed. Run: pip install feedparser")
        raise

    company = COMPANY_NAMES.get(symbol, symbol)
    headlines = []
    seen = set()   # deduplicate across feeds

    # Google News is our primary source — it aggregates ET, Moneycontrol, etc.
    feeds = [
        f"https://news.google.com/rss/search?q={company.replace(' ', '+')}+stock&hl=en-IN&gl=IN&ceid=IN:en",
        f"https://news.google.com/rss/search?q={symbol}+NSE+share&hl=en-IN&gl=IN&ceid=IN:en",
    ]

    cutoff = datetime.now() - timedelta(days=3)   # only last 3 days

    for feed_url in feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:max_per_feed]:
                title = entry.get('title', '').strip()
                if not title or title in seen:
                    continue

                seen.add(title)
                published = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6])
                    if published < cutoff:
                        continue

                headlines.append({
                    'title':     title,
                    'url':       entry.get('link', ''),
                    'published': published or datetime.now(),
                    'source':    feed.feed.get('title', 'google_news'),
                })
        except Exception as e:
            log.warning(f"  Feed fetch failed ({feed_url[:50]}...): {e}")
            continue

    log.debug(f"  {symbol}: {len(headlines)} headlines fetched")
    return headlines


def store_sentiment(stock_id: int, symbol: str, headlines: list, scores: list) -> int:
    """
    Upsert scored headlines into news_sentiment table.
    Returns number of rows stored.
    """
    conn   = get_conn()
    cursor = conn.cursor()
    stored = 0

    for h, s in zip(headlines, scores):
        # Use headline hash as dedup key — cleaner than storing full headline in UNIQUE
        headline_text = h['title'][:500]
        pub_date = h['published'].date() if h['published'] else date.today()

        try:
            cursor.execute("""
                INSERT INTO news_sentiment
                    (stock_id, date, headline, source, url,
                     sentiment, sentiment_score, relevance_score,
                     summary, scored_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (stock_id, date, headline) DO UPDATE SET
                    sentiment       = EXCLUDED.sentiment,
                    sentiment_score = EXCLUDED.sentiment_score,
                    scored_by       = EXCLUDED.scored_by
            """, (
                stock_id,
                pub_date,
                headline_text,
                h.get('source', 'google_news'),
                '',  # skip URL - Google News URLs contain % chars that confuse psycopg2
                s['sentiment'],
                s['score'],
                s['confidence'],   # use confidence as relevance proxy
                '',                # no summary in FinBERT mode
                'finbert',
            ))
            stored += 1
        except Exception as e:
            log.warning(f"  Row insert failed for {symbol}: {e}")

    conn.commit()
    cursor.close()
    conn.close()
    return stored


def collect_news_sentiment(watchlist_name: str = 'Default', target_symbol: str = None):
    """
    Main entry point. Iterates watchlist, fetches headlines, scores with
    FinBERT, stores results.
    """
    stocks = get_watchlist_stocks(watchlist_name)
    if target_symbol:
        stocks = [(sid, tok, sym, name) for sid, tok, sym, name in stocks
                  if sym == target_symbol.upper()]

    log.info(f"News sentiment collection starting — {len(stocks)} stocks")

    # Load model once before the loop
    _load_finbert()

    with refresh_log('news_sentiment') as rlog:
        total_stored = 0

        for stock_id, _, symbol, name in stocks:
            log.info(f"Processing {symbol} ({name})")

            # Fetch headlines
            headlines = fetch_rss_headlines(symbol)
            if not headlines:
                log.warning(f"  {symbol}: no headlines found")
                continue

            # Score with FinBERT
            titles  = [h['title'] for h in headlines]
            scores  = score_headlines(titles)

            # Store results
            n = store_sentiment(stock_id, symbol, headlines, scores)
            total_stored += n

            # Log summary
            if scores:
                avg_score = sum(s['score'] for s in scores) / len(scores)
                sentiment_summary = 'bullish' if avg_score > 0.1 else ('bearish' if avg_score < -0.1 else 'neutral')
                log.info(f"  {symbol}: {n} headlines stored | avg={avg_score:+.2f} ({sentiment_summary})")

            time.sleep(1)   # polite delay between stocks

        rlog['rows'] = total_stored

    log.info(f"News sentiment complete — {total_stored} rows stored")


def print_todays_sentiment():
    """Print a summary of today's news sentiment by stock."""
    conn   = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            s.tradingsymbol,
            COUNT(*) as headline_count,
            ROUND(AVG(ns.sentiment_score)::numeric, 2) as avg_score,
            SUM(CASE WHEN ns.sentiment = 'positive' THEN 1 ELSE 0 END) as positive,
            SUM(CASE WHEN ns.sentiment = 'negative' THEN 1 ELSE 0 END) as negative,
            SUM(CASE WHEN ns.sentiment = 'neutral'  THEN 1 ELSE 0 END) as neutral
        FROM news_sentiment ns
        JOIN stocks s ON ns.stock_id = s.id
        WHERE ns.date >= CURRENT_DATE - INTERVAL '3 days'
          AND ns.scored_by = 'finbert'
        GROUP BY s.tradingsymbol
        ORDER BY avg_score DESC
    """)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if not rows:
        log.info("No news sentiment data yet")
        return

    print(f"\n{'='*65}")
    print(f"NEWS SENTIMENT — last 3 days")
    print(f"{'='*65}")
    print(f"  {'Symbol':<14} {'Score':>6} {'Headlines':>10} {'Pos':>5} {'Neg':>5} {'Neu':>5}")
    print(f"  {'-'*55}")
    for sym, count, avg, pos, neg, neu in rows:
        icon = 'UP' if avg and avg > 0.1 else ('DN' if avg and avg < -0.1 else '--')
        avg_str = f"{avg:+.2f}" if avg else " 0.00"
        print(f"  {icon} {sym:<12} {avg_str:>6}  {count:>9}  {pos:>4}  {neg:>4}  {neu:>4}")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    import sys
    target = None
    if '--stock' in sys.argv:
        idx = sys.argv.index('--stock')
        if idx + 1 < len(sys.argv):
            target = sys.argv[idx + 1]

    collect_news_sentiment(target_symbol=target)
    print_todays_sentiment()
